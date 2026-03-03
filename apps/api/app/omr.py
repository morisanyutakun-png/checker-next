import io
import json
import os
from typing import List, Dict, Any, Optional

import fitz
import numpy as np
from PIL import Image, ImageOps
import cv2
import base64


# Global fixed box size (relative to page width/height). 管理画面では変更不可にします。
DEFAULT_BOX_W = 0.06
DEFAULT_BOX_H = 0.06
DEFAULT_BOX_Y = 0.2

# Static/global offsets (mm). Positive x -> right, positive y -> down
STATIC_DX_MM = 3   # +x 右へ(mm)
STATIC_DY_MM = -40.0  # +y 下へ(mm) なので、上に動かすならマイナス
# By default do NOT perform automatic fallback re-run when many patches are missing.
# This prevents silent re-grading that hides large user-provided offsets.
FALLBACK_NONE_RATIO = None
CLAMP_MM = 30.0
# If no `omr_offsets` present in config, apply this default downward shift (mm).
# Can be overridden by environment variable `OMR_DEFAULT_DY_MM`.
DEFAULT_GLOBAL_DY_MM = 8.0
# Runtime (Python) overrides. Use `set_runtime_offsets()` to change at runtime.
RUNTIME_DX_MM: Optional[float] = None
RUNTIME_DY_MM: Optional[float] = None
RUNTIME_FORCE_OVERRIDE: bool = False

def set_runtime_offsets(
    dx_mm: Optional[float],
    dy_mm: Optional[float],
    force: bool = True,
) -> None:
    """Set module-level runtime offsets for ``analyze_image`` / ``grade_pdf``.

    Args:
        dx_mm: horizontal offset in mm (positive → right), or *None*.
        dy_mm: vertical offset in mm (positive → down), or *None*.
        force: if *True*, runtime offsets override ``config['omr_offsets']``.
    """
    global RUNTIME_DX_MM, RUNTIME_DY_MM, RUNTIME_FORCE_OVERRIDE
    RUNTIME_DX_MM = None if dx_mm is None else float(dx_mm)
    RUNTIME_DY_MM = None if dy_mm is None else float(dy_mm)
    RUNTIME_FORCE_OVERRIDE = bool(force)


def clear_runtime_offsets() -> None:
    """Clear any runtime offsets previously set."""
    global RUNTIME_DX_MM, RUNTIME_DY_MM, RUNTIME_FORCE_OVERRIDE
    RUNTIME_DX_MM = None
    RUNTIME_DY_MM = None
    RUNTIME_FORCE_OVERRIDE = False


def pdf_to_images(pdf_bytes: bytes) -> List[Image.Image]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []
    for page in doc:
        # 300dpi推奨（精度↑、重さ↑）
        pix = page.get_pixmap(dpi=300, clip=page.rect)
        mode = "RGBA" if pix.alpha else "RGB"
        img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
        if img.mode != "RGB":
            img = img.convert("RGB")

        # landscape統一
        if img.width < img.height:
            img = img.rotate(90, expand=True)

        images.append(img)
    return images

def analyze_image(img: Image.Image, config: Dict[str, Any], dx_mm_override: Optional[float] = None, dy_mm_override: Optional[float] = None) -> Dict[str, Any]:
    """
    Drop-in replacement for your analyze_image().
    Fixes:
      - Unify page-mm coordinate origin to TOP-LEFT (x right, y down)
      - Robust fiducial detection using contours (not mean of black pixels)
      - Use Homography when 4 marks found (better for scan perspective)
      - Remove dangerous Y-flip fallback that caused bbox to jump to bottom
      - Evaluate bubble fill on a perspective-warped patch + inner inset (ignores border)
    """
    # --- basic ---
    # Accept either a PIL Image or a numpy grayscale array for easier testing.
    if isinstance(img, np.ndarray):
        # img is uint8 grayscale or RGB
        if img.ndim == 2:
            arr = img.astype(np.uint8)
            h, w = arr.shape
        else:
            # assume HxWx3 RGB
            arr = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.uint8)
            h, w = arr.shape
    else:
        w, h = img.size
        gray = ImageOps.grayscale(img)
        arr = np.array(gray)  # uint8, 0..255, origin: top-left

    # A4 landscape (generated sheets)
    PAGE_W_MM = 297.0
    PAGE_H_MM = 210.0

    threshold = float(config.get("threshold", 0.35))

    # -----------------------------
    # helpers
    # -----------------------------
    def _safe_float(v, default=0.0) -> float:
        try:
            return float(v)
        except Exception:
            return float(default)

    def _get_markgap_mm() -> float:
        # backward compatible:
        #   - config['omr_markgap_mm']
        #   - config['omr_marks']['markgap_mm']
        mg = _safe_float(config.get("omr_markgap_mm", 8.0), 8.0)
        try:
            om = config.get("omr_marks")
            if isinstance(om, dict) and isinstance(om.get("markgap_mm"), (int, float)):
                mg = float(om["markgap_mm"])
        except Exception:
            pass
        return mg

    def _get_offsets_mm(cfg: Dict[str, Any]) -> tuple[float, float, float, Any]:
        # config例:
        # omr_offsets: { dx_mm: 0.0, dy_mm: 0.0, clamp_mm: 30.0, fallback_none_ratio: 0.40 }
        om = cfg.get("omr_offsets") or {}
        raw_dx = om.get("dx_mm", 0.0)
        raw_dy = om.get("dy_mm", 0.0)
        dx = _safe_float(raw_dx, 0.0)
        dy = _safe_float(raw_dy, 0.0)
        # clamp_mm:
        #  - number: clamp offsets to [-clamp_mm, clamp_mm]
        #  - null/None: disable clamping (allow large offsets)
        clamp_raw = om.get("clamp_mm", None)
        if clamp_raw is None:
            clamp = None
        else:
            clamp = _safe_float(clamp_raw, None)

        # 暴走防止 (clamp が None の場合は無効化)
        if clamp is not None:
            dx_clamped = max(-clamp, min(clamp, dx))
            dy_clamped = max(-clamp, min(clamp, dy))
            dx, dy = dx_clamped, dy_clamped
        # fallback_none_ratio:
        #  - number: when ratio >= value, re-run with offsets disabled
        #  - null/None: disable fallback (do not re-run)
        fb_raw = om.get("fallback_none_ratio", None)
        if fb_raw is None:
            fb = None
        else:
            fb = _safe_float(fb_raw, 0.40)

        return float(dx), float(dy), (None if fb is None else float(fb)), clamp

    def _expected_mm_for_corner(corner: str, mg: float) -> tuple[float, float]:
        # mm origin: TOP-LEFT, y grows downward (same as image pixels)
        if corner == "nw":
            return (mg, mg)
        if corner == "ne":
            return (PAGE_W_MM - mg, mg)
        if corner == "sw":
            return (mg, PAGE_H_MM - mg)
        if corner == "se":
            return (PAGE_W_MM - mg, PAGE_H_MM - mg)
        return (mg, mg)

    def _positions_mm_override(mg: float) -> dict:
        """
        If config['omr_marks']['positions_mm'] exists, it is interpreted as:
          positions_mm: { name: {corner:'nw'|'ne'|'sw'|'se', dx_mm:..., dy_mm:...} }
        where dx_mm,dy_mm are offsets FROM THAT CORNER.
        We convert to absolute mm (origin top-left).
        """
        out = {}
        om = None
        try:
            om = config.get("omr_marks")
        except Exception:
            om = None

        positions = None
        try:
            if isinstance(om, dict) and isinstance(om.get("positions_mm"), dict):
                positions = om.get("positions_mm")
        except Exception:
            positions = None

        if not positions:
            return out

        for _, pinfo in positions.items():
            try:
                corner = pinfo.get("corner")
                if corner not in ("nw", "ne", "sw", "se"):
                    continue
                dx = _safe_float(pinfo.get("dx_mm", mg), mg)
                dy = _safe_float(pinfo.get("dy_mm", mg), mg)

                # Convert offset-from-corner -> absolute mm (TOP-LEFT origin)
                if corner == "nw":
                    mmx, mmy = dx, dy
                elif corner == "ne":
                    mmx, mmy = PAGE_W_MM - dx, dy
                elif corner == "sw":
                    mmx, mmy = dx, PAGE_H_MM - dy
                else:  # se
                    mmx, mmy = PAGE_W_MM - dx, PAGE_H_MM - dy

                out[corner] = (float(mmx), float(mmy))
            except Exception:
                continue
        return out

    def _find_contours(binary_img: np.ndarray):
        # OpenCV version compatibility
        cnts = cv2.findContours(binary_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if len(cnts) == 2:
            contours, _ = cnts
        else:
            _, contours, _ = cnts
        return contours

    def detect_fiducials_and_transform(gray_arr: np.ndarray) -> dict | None:
        """
        Detect corner marks and compute mm->px transform.
        Prefer homography when >=4 points; fallback to affine when >=3.
        """
        gh, gw = gray_arr.shape
        mg = _get_markgap_mm()
        pos_override = _positions_mm_override(mg)

        # approx pixels per mm
        px_per_mm_x = gw / PAGE_W_MM
        px_per_mm_y = gh / PAGE_H_MM

        # search window (mm) — increase to tolerate marks placed further from edges
        search_mm = 60.0
        sx = int(search_mm * px_per_mm_x)
        sy = int(search_mm * px_per_mm_y)

        corners_win = {
            "nw": (0, 0, sx, sy),
            "ne": (max(0, gw - sx), 0, sx, sy),
            "sw": (0, max(0, gh - sy), sx, sy),
            "se": (max(0, gw - sx), max(0, gh - sy), sx, sy),
        }

        detected = {}  # corner -> (cx,cy)
        debug_candidates = {}

        # Parameters for filtering candidate blobs
        # (tuned to be tolerant; refine later if needed)
        # allow smaller marks by reducing minimum-area threshold
        min_area = max(12, int((sx * sy) * 0.0005))   # tolerant lower bound
        max_area = int((sx * sy) * 0.20)              # <= 20% of window

        for corner, (ox, oy, rw, rh) in corners_win.items():
            win = gray_arr[oy:oy + rh, ox:ox + rw]
            if win.size == 0:
                continue

            # binarize: marks are dark -> want them white in mask
            blur = cv2.GaussianBlur(win, (5, 5), 0)
            _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            inv = 255 - th  # dark becomes white

            contours = _find_contours(inv)
            cand = []

            for c in contours:
                area = cv2.contourArea(c)
                if area < min_area or area > max_area:
                    continue

                x, y, ww, hh = cv2.boundingRect(c)
                if ww <= 0 or hh <= 0:
                    continue

                # aspect ratio close to 1 (square-ish mark)
                ar = ww / float(hh)
                if ar < 0.5 or ar > 2.0:
                    continue

                # solidity-ish: area relative to bbox (filled mark tends to be dense)
                box_area = ww * hh
                fill_ratio = area / float(box_area) if box_area > 0 else 0.0
                if fill_ratio < 0.15:
                    continue

                # centroid
                M = cv2.moments(c)
                if M["m00"] == 0:
                    continue
                cx = (M["m10"] / M["m00"]) + ox
                cy = (M["m01"] / M["m00"]) + oy

                # prefer closer to the actual corner
                target_x = 0 if corner in ("nw", "sw") else (gw - 1)
                target_y = 0 if corner in ("nw", "ne") else (gh - 1)
                dist = float(np.hypot(cx - target_x, cy - target_y))

                # smaller dist is better; higher fill_ratio is better; moderate area is ok
                score = (-dist) + (fill_ratio * 50.0)

                cand.append((score, float(cx), float(cy), float(area), float(fill_ratio), (x + ox, y + oy, ww, hh)))

            debug_candidates[corner] = cand[:]
            if not cand:
                continue

            cand.sort(key=lambda t: t[0], reverse=True)
            best = cand[0]
            detected[corner] = (best[1], best[2])

        if len(detected) < 3:
            return None

        # Build correspondences (mm -> px)
        src_mm = []
        dst_px = []
        used = []

        for corner, (px, py) in detected.items():
            if corner in pos_override:
                mmx, mmy = pos_override[corner]
            else:
                mmx, mmy = _expected_mm_for_corner(corner, mg)

            src_mm.append([mmx, mmy])
            dst_px.append([px, py])
            used.append(corner)

        src = np.array(src_mm, dtype=np.float32)
        dst = np.array(dst_px, dtype=np.float32)

        # Compute transform
        H = None
        A = None

        if len(src_mm) >= 4:
            # Homography (projective) – robust for scan perspective
            H, mask = cv2.findHomography(src, dst, method=cv2.RANSAC, ransacReprojThreshold=5.0)
            if H is None:
                # fallback later
                pass

        if H is None and len(src_mm) >= 3:
            # Affine with RANSAC when possible
            if len(src_mm) >= 4:
                A, inliers = cv2.estimateAffine2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=5.0)
            else:
                # exactly 3 points
                A = cv2.getAffineTransform(src[:3], dst[:3])

        if H is None and A is None:
            return None

        def mm_to_px(mx: float, my: float) -> tuple[float, float]:
            if H is not None:
                v = np.array([mx, my, 1.0], dtype=np.float64)
                p = H @ v
                # avoid hard zero-division causing repeated (0,0) mappings
                denom = float(p[2])
                if abs(denom) < 1e-6:
                    denom = 1e-6
                return float(p[0] / denom), float(p[1] / denom)
            else:
                # A is 2x3
                x = A[0, 0] * mx + A[0, 1] * my + A[0, 2]
                y = A[1, 0] * mx + A[1, 1] * my + A[1, 2]
                return float(x), float(y)

        # residuals
        residuals = []
        try:
            for i, (mx, my) in enumerate(src_mm):
                ex, ey = mm_to_px(float(mx), float(my))
                dx = ex - float(dst_px[i][0])
                dy = ey - float(dst_px[i][1])
                residuals.append({
                    "corner": used[i],
                    "expected_px": [float(ex), float(ey)],
                    "detected_px": [float(dst_px[i][0]), float(dst_px[i][1])],
                    "delta": [float(dx), float(dy)],
                    "dist": float(np.hypot(dx, dy)),
                })
        except Exception:
            residuals = []

        return {
            "mm_to_px": mm_to_px,
            "detected": detected,
            "H": H.tolist() if H is not None else None,
            "A": A.tolist() if A is not None else None,
            "src_mm": src_mm,
            "dst_px": dst_px,
            "residuals": residuals,
            "debug_candidates": debug_candidates,  # optional (remove if too heavy)
        }

    def extract_patch_and_bbox(gray_arr: np.ndarray, ch: Dict[str, Any], mm_to_px_fn, dx_mm: float = 0.0, dy_mm: float = 0.0):
        """
        Return:
          bbox_px: [x,y,w,h]  (axis-aligned bounding rect)
          poly_px: [[x,y]x4]  (mapped quadrilateral)
          patch: normalized grayscale patch (warped to rectangle) for scoring
        """
        gh, gw = gray_arr.shape

        # relative -> mm
        x_rel = _safe_float(ch.get("x", 0.0), 0.0)
        y_rel = _safe_float(ch.get("y", 0.0), 0.0)
        w_rel = _safe_float(ch.get("w", 0.0), 0.0)
        h_rel = _safe_float(ch.get("h", 0.0), 0.0)

        if w_rel <= 0 or h_rel <= 0:
            return [0, 0, 0, 0], None, None

        x_mm = x_rel * PAGE_W_MM
        y_mm = y_rel * PAGE_H_MM
        w_mm = w_rel * PAGE_W_MM
        h_mm = h_rel * PAGE_H_MM

        # ✅ 安全なオフセット（mm、左上原点、y下向き）
        x_mm += float(dx_mm)
        y_mm += float(dy_mm)

        if mm_to_px_fn is None:
            # fallback: direct relative bbox on pixels
            x0 = int(max(0, min(int(x_rel * gw), gw - 1)))
            y0 = int(max(0, min(int(y_rel * gh), gh - 1)))
            x1 = int(max(0, min(int((x_rel + w_rel) * gw), gw)))
            y1 = int(max(0, min(int((y_rel + h_rel) * gh), gh)))
            # Apply mm offsets in pixel-fallback by converting mm -> px
            try:
                dx_px = int(round(float(dx_mm) * (gw / PAGE_W_MM))) if dx_mm is not None else 0
                dy_px = int(round(float(dy_mm) * (gh / PAGE_H_MM))) if dy_mm is not None else 0
            except Exception:
                dx_px = 0
                dy_px = 0

            x0 = max(0, min(gw - 1, x0 + dx_px))
            x1 = max(0, min(gw, x1 + dx_px))
            y0 = max(0, min(gh - 1, y0 + dy_px))
            y1 = max(0, min(gh, y1 + dy_px))
            bw = max(1, x1 - x0)
            bh = max(1, y1 - y0)
            bbox = [x0, y0, bw, bh]
            patch = gray_arr[y0:y0 + bh, x0:x0 + bw]
            return bbox, None, patch

        # map box corners (mm origin top-left)
        p0 = mm_to_px_fn(x_mm, y_mm)               # top-left
        p1 = mm_to_px_fn(x_mm + w_mm, y_mm)        # top-right
        p2 = mm_to_px_fn(x_mm + w_mm, y_mm + h_mm) # bottom-right
        p3 = mm_to_px_fn(x_mm, y_mm + h_mm)        # bottom-left

        poly = np.array([p0, p1, p2, p3], dtype=np.float32)

        xs = poly[:, 0]
        ys = poly[:, 1]
        # Do not clamp coordinates to image bounds here; keep raw projected values.
        bx0 = int(np.floor(xs.min()))
        by0 = int(np.floor(ys.min()))
        bx1 = int(np.ceil(xs.max()))
        by1 = int(np.ceil(ys.max()))

        # If computed box is degenerate, expand minimally to avoid collapsing many boxes
        if bx1 <= bx0:
            bx1 = bx0 + 10
        if by1 <= by0:
            by1 = by0 + 10

        bbox = [bx0, by0, int(bx1 - bx0), int(by1 - by0)]

        # perspective-warp to a canonical rectangle for stable scoring
        # compute target size from edge lengths
        def _dist(a, b):
            return float(np.hypot(a[0] - b[0], a[1] - b[1]))

        width_px = int(max(_dist(p0, p1), _dist(p3, p2), 10.0))
        height_px = int(max(_dist(p0, p3), _dist(p1, p2), 10.0))

        # clamp sizes
        width_px = max(10, min(width_px, 800))
        height_px = max(10, min(height_px, 800))

        dst = np.array([
            [0.0, 0.0],
            [float(width_px - 1), 0.0],
            [float(width_px - 1), float(height_px - 1)],
            [0.0, float(height_px - 1)],
        ], dtype=np.float32)

        M = cv2.getPerspectiveTransform(poly, dst)

        # intersection area with image — still compute but do NOT bail out early.
        xs = poly[:, 0]
        ys = poly[:, 1]
        bx0 = int(np.floor(xs.min()))
        by0 = int(np.floor(ys.min()))
        bx1 = int(np.ceil(xs.max()))
        by1 = int(np.ceil(ys.max()))

        ix0 = max(0, bx0)
        iy0 = max(0, by0)
        ix1 = min(gw, bx1)
        iy1 = min(gh, by1)
        inter_w = max(0, ix1 - ix0)
        inter_h = max(0, iy1 - iy0)

        # Even when the intersection is small we prefer returning a warped patch
        # (with constant white border) so the UI can show a thumbnail instead
        # of nothing. This avoids silent missing thumbnails; downstream logic
        # can still detect tiny/intersecting patches via size/resolution.

        # Use constant border (white) to avoid stretched-edge replication creating identical patches
        patch = cv2.warpPerspective(
            gray_arr, M, (width_px, height_px),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=255
        )

        return bbox, poly.tolist(), patch

    def score_patch(patch: np.ndarray):
        """
        Score filled ratio on inner area (ignore border).
        Returns: score, dark, total, thumb_b64
        """
        if patch is None or patch.size == 0:
            return 0.0, 0, 1, None

        ph, pw = patch.shape[:2]
        # inner inset to ignore printed border/frame
        mx = int(pw * 0.18)
        my = int(ph * 0.18)
        x0 = max(0, mx)
        y0 = max(0, my)
        x1 = min(pw, pw - mx)
        y1 = min(ph, ph - my)
        core = patch[y0:y1, x0:x1] if (x1 > x0 + 4 and y1 > y0 + 4) else patch

        blur = cv2.GaussianBlur(core, (5, 5), 0)
        _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        dark = int(np.sum(th == 0))
        total = int(th.size) if th.size > 0 else 1
        score = float(dark) / float(total)

        # thumbnail
        thumb_b64 = None
        try:
            pil_img = Image.fromarray(core).convert("RGB")
            pil_img.thumbnail((160, 120))
            bio = io.BytesIO()
            pil_img.save(bio, format="PNG")
            thumb_b64 = "data:image/png;base64," + base64.b64encode(bio.getvalue()).decode("ascii")
        except Exception:
            thumb_b64 = None

        return float(score), int(dark), int(total), thumb_b64

    # -----------------------------
    # compute transform (fiducials)
    # -----------------------------
    tfm = detect_fiducials_and_transform(arr)
    mm_to_px_fn = tfm["mm_to_px"] if tfm is not None else None

    fiducial_info = None
    if tfm is not None:
        fiducial_info = {
            "detected": tfm.get("detected"),
            "H": tfm.get("H"),
            "A": tfm.get("A"),
            "src_mm": tfm.get("src_mm"),
            "dst_px": tfm.get("dst_px"),
            "residuals": tfm.get("residuals"),
        }

    # -----------------------------
    # grade questions (supports re-run with different dx/dy offsets)
    # -----------------------------
    # Support multiple input shapes:
    #  - config['questions'] (preferred)
    #  - config['questions_meta']['questions'] (legacy generated JSON)
    raw_questions = None
    if config.get("questions"):
        raw_questions = config.get("questions")
    else:
        qm = config.get("questions_meta") or {}
        raw_questions = qm.get("questions") or []

    # Heuristic: detect if many bubbles have out-of-range y_mm (negative or far off page).
    expected_y_by_index = {}
    try:
        ys = []
        bad_count = 0
        total_checked = 0
        for i, qn in enumerate((raw_questions or [])[:12]):
            b0 = None
            try:
                b0 = (qn.get("choices") or qn.get("bubbles") or [None])[0]
            except Exception:
                b0 = None
            if isinstance(b0, dict):
                total_checked += 1
                yv = None
                if b0.get("y_mm") is not None:
                    yv = float(b0.get("y_mm"))
                elif b0.get("y_mm_top") is not None:
                    # y_mm_top is distance from top; convert to bottom-origin mm for consistency
                    yv = PAGE_H_MM - float(b0.get("y_mm_top"))
                if yv is not None:
                    ys.append((i, yv))
                    if yv < 0 or yv > PAGE_H_MM:
                        bad_count += 1
        # If a majority of sampled rows have bad y coordinates, compute expected linear spacing
        if total_checked > 0 and bad_count >= max(2, total_checked // 2) and len(ys) >= 2:
            deltas = []
            for k in range(len(ys) - 1):
                deltas.append(ys[k + 1][1] - ys[k][1])
            if deltas:
                avg_delta = float(sum(deltas) / float(len(deltas)))
                base_idx, base_y = ys[0]
                for qi in range(len(raw_questions or [])):
                    expected_y_by_index[qi] = float(base_y + (qi - base_idx) * avg_delta)
    except Exception:
        expected_y_by_index = {}

    dx_mm, dy_mm, fallback_none_ratio, clamp_mm = _get_offsets_mm(config)

    # Priority order for offsets (highest -> lowest):
    #  1) explicit function call overrides (dx_mm_override/dy_mm_override)
    #  2) runtime Python overrides set by set_runtime_offsets() (optionally forced)
    #  3) config['omr_offsets'] (from _get_offsets_mm)
    #  4) default Python-side downward shift (env or DEFAULT_GLOBAL_DY_MM)
    try:
        if dx_mm_override is not None:
            dx_mm = float(dx_mm_override)
        if dy_mm_override is not None:
            dy_mm = float(dy_mm_override)
    except Exception:
        pass

    # Apply runtime overrides if set and either forced or no explicit config offsets present
    try:
        if (RUNTIME_DX_MM is not None or RUNTIME_DY_MM is not None):
            has_cfg_offsets = ('omr_offsets' in config) and bool(config.get('omr_offsets'))
            if RUNTIME_FORCE_OVERRIDE or (not has_cfg_offsets):
                try:
                    if RUNTIME_DX_MM is not None:
                        dx_mm = float(RUNTIME_DX_MM)
                    if RUNTIME_DY_MM is not None:
                        dy_mm = float(RUNTIME_DY_MM)
                    warnings.append({
                        'type': 'runtime_override_applied',
                        'message': 'Applied runtime Python offsets',
                        'runtime_offsets_mm': [RUNTIME_DX_MM, RUNTIME_DY_MM],
                        'resulting_offsets_mm': [dx_mm, dy_mm],
                    })
                except Exception:
                    pass
    except Exception:
        pass

    # If the user did not provide explicit omr_offsets (or provided dy==0),
    # apply a default downward shift so extracted patches sit lower on the page.
    # The default can be overridden with the environment variable
    # `OMR_DEFAULT_DY_MM` (e.g. export OMR_DEFAULT_DY_MM=10.0).
    try:
        env_val = os.getenv('OMR_DEFAULT_DY_MM')
        if env_val is not None:
            try:
                default_dy = float(env_val)
            except Exception:
                default_dy = float(DEFAULT_GLOBAL_DY_MM)
        else:
            default_dy = float(DEFAULT_GLOBAL_DY_MM)

        # Apply when omr_offsets missing/empty or when dy_mm is exactly 0.0
        has_omr_offsets = ('omr_offsets' in config) and bool(config.get('omr_offsets'))
        # Only apply Python-side default when caller did NOT pass an override
        caller_overrode = (dx_mm_override is not None) or (dy_mm_override is not None)
        if (not caller_overrode) and ((not has_omr_offsets) or (abs(float(dy_mm)) < 1e-9)):
            dy_mm = float(dy_mm) + float(default_dy)
            warnings.append({
                'type': 'default_downward_shift_applied',
                'message': 'Applied default downward OMR shift (Python-side)',
                'default_dy_mm': float(default_dy),
                'resulting_dy_mm': float(dy_mm),
            })
    except Exception:
        pass
    warnings = []

    # record raw config for debugging
    raw_omr_offsets = (config.get('omr_offsets') or {})

    # if clamp was applied, and it changed the requested value, add a warning
    try:
        req_dx = float((config.get('omr_offsets') or {}).get('dx_mm', 0.0))
        req_dy = float((config.get('omr_offsets') or {}).get('dy_mm', 0.0))
        if clamp_mm is not None:
            if abs(req_dx - dx_mm) > 1e-6 or abs(req_dy - dy_mm) > 1e-6:
                warnings.append({
                    'type': 'offset_clamped',
                    'message': 'Offsets were clamped to configured clamp_mm',
                    'requested_offsets_mm': [req_dx, req_dy],
                    'applied_offsets_mm': [dx_mm, dy_mm],
                    'clamp_mm': float(clamp_mm),
                })
    except Exception:
        pass
    def _normalize_grid_if_needed(questions: list):
        """
        If many questions share the same normalized `y` (template-style JSON),
        infer the number of columns from the first question and spread questions
        downwards into rows so each question gets a distinct `y`.
        This allows using the provided JSON without editing it.
        """
        try:
            if not questions or len(questions) <= 1:
                return
            ys = [float(q.get('y', DEFAULT_BOX_Y)) for q in questions]
            # if all y nearly equal, we assume template-style layout
            if max(ys) - min(ys) > 1e-6:
                return

            first = questions[0]
            # determine number of columns by scanning question `x` positions
            # on the first row (questions that share the same y as the first)
            ncols = 0
            try:
                start_y = float(first.get('y', DEFAULT_BOX_Y))
            except Exception:
                start_y = float(DEFAULT_BOX_Y)

            xs = []
            scan_n = min(40, len(questions))
            for q in questions[:scan_n]:
                try:
                    qy = float(q.get('y', start_y))
                    if abs(qy - start_y) <= 1e-3:
                        xs.append(float(q.get('x', 0.0)))
                except Exception:
                    continue
            xs = sorted(set(xs))
            if xs:
                ncols = len(xs)

            # fallback: if we couldn't find columns from question x positions,
            # try to use num_choices on the first question (legacy heuristic)
            if ncols == 0:
                try:
                    ncols = int(first.get('num_choices') or 0)
                except Exception:
                    ncols = 0
            if ncols <= 0:
                return

            n_questions = len(questions)
            nrows = (n_questions + ncols - 1) // ncols

            start_y = float(first.get('y', DEFAULT_BOX_Y))
            bottom_margin = 0.05
            if nrows > 1:
                stepy = (1.0 - start_y - bottom_margin) / float(max(1, nrows - 1))
            else:
                stepy = 0.0

            # remember original common y to detect per-choice defaults
            orig_y = float(first.get('y', DEFAULT_BOX_Y))
            for idx, q in enumerate(questions):
                row = idx // ncols
                try:
                    new_y = float(start_y + row * stepy)
                except Exception:
                    new_y = float(start_y)
                q['y'] = new_y

                # propagate to per-choice `y` when those choices use the template y
                try:
                    chs = q.get('choices') or []
                    for c in chs:
                        try:
                            cy = c.get('y')
                            if cy is None:
                                continue
                            if abs(float(cy) - orig_y) <= 1e-6:
                                c['y'] = float(new_y)
                        except Exception:
                            continue
                except Exception:
                    pass
        except Exception:
            return

    # Normalize template-style questions (same y) into grid rows
    try:
        _normalize_grid_if_needed(raw_questions)
    except Exception:
        pass

    def _convert_bubble_mm_to_norm(b):
        # replicate helper into local scope for closure
        if isinstance(b, dict) and ("x" in b or "w" in b):
            return b

        x_mm = None
        y_mm = None
        w_mm = None
        h_mm = None
        if isinstance(b, dict):
            x_mm = b.get("x_mm") if b.get("x_mm") is not None else b.get("left_mm")
            if b.get("y_mm_top") is not None:
                y_mm = float(b.get("y_mm_top"))
            else:
                y_mm = b.get("y_mm") if b.get("y_mm") is not None else b.get("top_mm")
            w_mm = b.get("width_mm") if b.get("width_mm") is not None else b.get("w_mm")
            h_mm = b.get("height_mm") if b.get("height_mm") is not None else b.get("h_mm")

        try:
            if x_mm is None or y_mm is None or w_mm is None or h_mm is None:
                return b

            x = float(x_mm) / PAGE_W_MM
            y = float(y_mm) / PAGE_H_MM
            wv = float(w_mm) / PAGE_W_MM
            hv = float(h_mm) / PAGE_H_MM
            out = {"x": float(x), "y": float(y), "w": float(wv), "h": float(hv)}
            if isinstance(b, dict) and "label" in b:
                out["label"] = b.get("label")
            return out
        except Exception:
            return b

    def grade_questions(run_dx_mm: float, run_dy_mm: float):
        results_local = []
        for q_index, q in enumerate((raw_questions or [])):
            choices_cfg = q.get("choices") or q.get("bubbles") or []

            # perform conversion in-place if necessary
            if choices_cfg and isinstance(choices_cfg, list):
                first = choices_cfg[0] if len(choices_cfg) > 0 else None
                has_mm = isinstance(first, dict) and ("x_mm" in first or "width_mm" in first or "w_mm" in first)
                if has_mm:
                    converted = []
                    for b in choices_cfg:
                        converted.append(_convert_bubble_mm_to_norm(b))

                    if expected_y_by_index and expected_y_by_index.get(q_index) is not None:
                        try:
                            ey_mm = float(expected_y_by_index.get(q_index))
                            for cb in converted:
                                if isinstance(cb, dict):
                                    cb["y"] = float(ey_mm) / PAGE_H_MM
                        except Exception:
                            pass

                    choices_cfg = converted

                if isinstance(choices_cfg, list) and len(choices_cfg) == 1:
                    first = choices_cfg[0]
                    try:
                        num_choices = int(q.get("num_choices") or 5)
                    except Exception:
                        num_choices = 5

                    fx = float(first.get("x", 0.0))
                    fw = float(first.get("w", 0.0))
                    fy = float(first.get("y", DEFAULT_BOX_Y))
                    fh = float(first.get("h", DEFAULT_BOX_H))

                    if fw > 0.05 and num_choices > 1:
                        parts = []
                        seg = fw / float(num_choices)
                        for i in range(num_choices):
                            parts.append({
                                "x": float(fx + seg * i),
                                "y": float(fy),
                                "w": float(seg),
                                "h": float(fh),
                                "label": str(i + 1),
                            })
                        choices_cfg = parts

            # auto choices if num_choices provided
            if (not choices_cfg) and q.get("num_choices"):
                n = int(q.get("num_choices"))
                if n > 0:
                    start_x = _safe_float(q.get("x_start", 0.1), 0.1)
                    end_x = _safe_float(q.get("x_end", 0.9), 0.9)
                    span = max(0.001, end_x - start_x)
                    step = span / max(n, 1)
                    y = _safe_float(q.get("y", DEFAULT_BOX_Y), DEFAULT_BOX_Y)
                    wbox = _safe_float(q.get("box_w", DEFAULT_BOX_W), DEFAULT_BOX_W)
                    hbox = _safe_float(q.get("box_h", DEFAULT_BOX_H), DEFAULT_BOX_H)

                    choices_cfg = []
                    for i in range(n):
                        cx = start_x + step * i + (step - wbox) / 2.0
                        choices_cfg.append({"x": cx, "y": y, "w": wbox, "h": hbox})

            qres = {
                "id": q.get("id"),
                "label": q.get("label"),
                "choices": [],
                "answer": q.get("answer"),
            }

            best_idx = None
            best_score = 0.0

            mapped_centers_list = []
            source_centers_mm_list = []
            for idx, ch in enumerate(choices_cfg):
                # extract patch (pass offsets)
                bbox_px, poly_px, patch = extract_patch_and_bbox(arr, ch, mm_to_px_fn, run_dx_mm, run_dy_mm)

                # Debug: record mapped center (mm -> px) for this choice so we can detect
                # when mapping collapses to identical coordinates across many choices.
                mapped_center = None
                try:
                    x_rel = _safe_float(ch.get("x", 0.0), 0.0) 
                    y_rel = _safe_float(ch.get("y", 0.0), 0.0)
                    w_rel = _safe_float(ch.get("w", 0.0), 0.0)
                    h_rel = _safe_float(ch.get("h", 0.0), 0.0)
                    cx_mm = (x_rel + w_rel * 0.5) * PAGE_W_MM
                    cy_mm = (y_rel + h_rel * 0.5) * PAGE_H_MM
                    # ✅ 同じオフセットを反映（診断ずれ防止）
                    cx_mm += float(run_dx_mm)
                    cy_mm += float(run_dy_mm)

                    


                    if mm_to_px_fn is not None:
                        mcx, mcy = mm_to_px_fn(cx_mm, cy_mm)
                        mapped_center = [float(mcx), float(mcy)]
                    else:
                        mcx = int(max(0, min(int((x_rel + w_rel * 0.5) * (arr.shape[1])), arr.shape[1] - 1)))
                        mcy = int(max(0, min(int((y_rel + h_rel * 0.5) * (arr.shape[0])), arr.shape[0] - 1)))
                        mapped_center = [int(mcx), int(mcy)]
                except Exception:
                    mapped_center = None
                try:
                    source_centers_mm_list.append([float(cx_mm), float(cy_mm)])
                except Exception:
                    source_centers_mm_list.append(None)
                mapped_centers_list.append(tuple(mapped_center) if mapped_center is not None else None)

                # score patch
                score, dark, total, thumb_b64 = score_patch(patch)

                # label passthrough
                label = None
                try:
                    if isinstance(ch, dict) and "label" in ch:
                        label = ch.get("label")
                except Exception:
                    label = None

                qres["choices"].append({
                    "index": int(idx),
                    "score": float(score),
                    "label": label,
                    "bbox_px": [int(bbox_px[0]), int(bbox_px[1]), int(bbox_px[2]), int(bbox_px[3])],
                    "poly_px": poly_px,  # for debug UI (optional)
                    "dark_pixels": int(dark),
                    "total_pixels": int(total),
                    "thumb_b64": thumb_b64,
                    "mapped_center_px": mapped_center,
                    "source_center_mm": source_centers_mm_list[-1],
                })

                if score > best_score:
                    best_score = float(score)
                    best_idx = int(idx)

            selected = best_idx if (best_idx is not None and best_score >= threshold) else None
            qres["selected_index"] = selected
            qres["selected_score"] = float(best_score)
            # Only mark correct when there is a selected choice and an expected answer.
            # Prevent accidental True when both are None or missing.
            try:
                expected = q.get("answer")
                if expected is None or selected is None:
                    is_correct = False
                else:
                    # coerce numeric answers to int if possible
                    try:
                        is_correct = int(selected) == int(expected)
                    except Exception:
                        # fallback: compare as strings
                        is_correct = str(selected) == str(expected)
            except Exception:
                is_correct = False
            qres["correct"] = bool(is_correct)
            try:
                total_mapped = len([m for m in mapped_centers_list if m is not None])
                unique_mapped = len(set([m for m in mapped_centers_list if m is not None]))
                duplicates = total_mapped - unique_mapped
                qres["mapping_stats"] = {
                    "total_mapped": int(total_mapped),
                    "unique_mapped": int(unique_mapped),
                    "duplicates": int(duplicates),
                    "mapped_centers_sample": mapped_centers_list[:8],
                }
            except Exception:
                qres["mapping_stats"] = None

            results_local.append(qres)
        return results_local

    # 1st pass with configured offsets
    results = grade_questions(dx_mm, dy_mm)

    # --- auto vertical shift: estimate median dy (pixels) required to bring
    # mapped centers into their bounding boxes, convert to mm and re-run once.
    def _estimate_auto_shift_mm(results_list):
        try:
            gw = arr.shape[1]
            gh = arr.shape[0]
            # pixels per mm (x and y)
            px_per_mm_x = float(gw) / PAGE_W_MM
            px_per_mm_y = float(gh) / PAGE_H_MM

            dx_pixels = []
            dy_pixels = []
            for q in (results_list or []):
                for c in (q.get('choices') or []):
                    mc = c.get('mapped_center_px')
                    bb = c.get('bbox_px')
                    if not mc or not bb:
                        continue
                    try:
                        mcx, mcy = float(mc[0]), float(mc[1])
                        bx, by, bw, bh = int(bb[0]), int(bb[1]), int(bb[2]), int(bb[3])
                    except Exception:
                        continue
                    # center of bbox
                    bc_x = float(bx) + float(bw) * 0.5
                    bc_y = float(by) + float(bh) * 0.5
                    # required shift in pixels to align mapped center to bbox center
                    dx_px = float(bc_x) - float(mcx)
                    dy_px = float(bc_y) - float(mcy)
                    # ignore huge outliers (likely bad mapping)
                    if abs(dx_px) <= max(1.0, bw * 2.0, 200.0):
                        dx_pixels.append(dx_px)
                    if abs(dy_px) <= max(1.0, bh * 2.0, 200.0):
                        dy_pixels.append(dy_px)

            def median_from_list(vals):
                if not vals:
                    return 0.0
                s = sorted(vals)
                m = len(s)
                if m % 2 == 1:
                    return s[m // 2]
                return 0.5 * (s[m // 2 - 1] + s[m // 2])

            med_dx_px = median_from_list(dx_pixels)
            med_dy_px = median_from_list(dy_pixels)

            # convert px -> mm for both axes
            dx_mm = float(med_dx_px) / px_per_mm_x if px_per_mm_x != 0 else 0.0
            dy_mm = float(med_dy_px) / px_per_mm_y if px_per_mm_y != 0 else 0.0
            return float(dx_mm), float(dy_mm)
        except Exception:
            return 0.0, 0.0

    # If user wants automatic nudging, estimate X/Y shifts and optionally apply once
    auto_shift_mm = [0.0, 0.0]
    try:
        # read auto-shift config (default: enabled)
        auto_shift_enabled = True
        try:
            aso = (config.get('omr_offsets') or {}).get('auto_shift')
            if aso is not None:
                auto_shift_enabled = bool(aso)
        except Exception:
            auto_shift_enabled = True

        suggested_dx_mm, suggested_dy_mm = _estimate_auto_shift_mm(results)
        # require at least 2 mm of shift to apply automatically (avoid noise)
        auto_shift_threshold = 2.0
        try:
            tconf = (config.get('omr_offsets') or {}).get('auto_shift_threshold_mm')
            if tconf is not None:
                auto_shift_threshold = float(tconf)
        except Exception:
            pass

        # if auto-shift disabled, record suggested value for debugging but do not apply
        if not auto_shift_enabled:
            # store the suggestion for debug visibility
            auto_shift_mm = [0.0, 0.0]
            if abs(suggested_dx_mm) >= auto_shift_threshold or abs(suggested_dy_mm) >= auto_shift_threshold:
                warnings.append({
                    'type': 'auto_shift_skipped',
                    'message': 'Auto-shift suggested but disabled by config',
                    'suggested_shift_mm': [float(suggested_dx_mm), float(suggested_dy_mm)],
                    'original_offsets_mm': [dx_mm, dy_mm],
                })
        else:
            if abs(suggested_dx_mm) >= auto_shift_threshold or abs(suggested_dy_mm) >= auto_shift_threshold:
                # obey clamp only if clamp was explicitly configured (clamp_mm variable)
                adx = float(suggested_dx_mm)
                ady = float(suggested_dy_mm)
                if clamp_mm is not None:
                    try:
                        clamp_val = float(clamp_mm)
                        if abs(adx) > clamp_val or abs(ady) > clamp_val:
                            warnings.append({
                                'type': 'auto_shift_clamped',
                                'message': 'Auto-shift suggestion was clamped by clamp_mm',
                                'suggested_before_clamp_mm': [float(adx), float(ady)],
                                'clamp_mm': float(clamp_val),
                            })
                        adx = max(-clamp_val, min(clamp_val, adx))
                        ady = max(-clamp_val, min(clamp_val, ady))
                    except Exception:
                        pass

                # apply suggested shift and re-run grading once (apply both axes)
                auto_shift_mm = [float(adx), float(ady)]
                if auto_shift_mm[0] != 0.0 or auto_shift_mm[1] != 0.0:
                    results = grade_questions(dx_mm + auto_shift_mm[0], dy_mm + auto_shift_mm[1])
                    # record a warning that auto-shift was applied
                    warnings.append({
                        'type': 'auto_shift_applied',
                        'message': 'Auto-applied X/Y shift to improve alignment',
                        'suggested_shift_mm': [float(auto_shift_mm[0]), float(auto_shift_mm[1])],
                        'original_offsets_mm': [dx_mm, dy_mm],
                    })
            else:
                auto_shift_mm = [0.0, 0.0]
    except Exception:
        pass

    # Check ratio of missing patches (thumb_b64==None is a proxy for patch==None)
    try:
        total = 0
        none_count = 0
        for q in results:
            for c in (q.get("choices") or []):
                total += 1
                if c.get("thumb_b64") is None:
                    none_count += 1
        ratio = (none_count / total) if total > 0 else 0.0
    except Exception:
        ratio = 0.0

    # If too many missing patches and offsets were non-zero, re-run with offsets disabled
    # If `fallback_none_ratio` is None, do NOT perform the fallback (allow out-of-bounds offsets).
    used_offsets = [dx_mm, dy_mm]
    if (fallback_none_ratio is not None) and (ratio >= float(fallback_none_ratio)) and (dx_mm != 0.0 or dy_mm != 0.0):
        warnings.append({
            "type": "offset_fallback",
            "message": "Too many patches were None with offsets; re-graded with offsets disabled.",
            "none_ratio": ratio,
            "used_offsets_mm": [dx_mm, dy_mm],
        })
        # re-grade with offsets disabled
        results = grade_questions(0.0, 0.0)
        used_offsets = [0.0, 0.0]

    out = {"width": int(w), "height": int(h), "questions": results}
    # record offsets actually used for this page (after possible fallback)
    try:
        out["omr_offsets_used_mm"] = [float(used_offsets[0]), float(used_offsets[1])]
    except Exception:
        out["omr_offsets_used_mm"] = [0.0, 0.0]

    # debug info about offsets
    try:
        req_dx = float((config.get('omr_offsets') or {}).get('dx_mm', 0.0))
        req_dy = float((config.get('omr_offsets') or {}).get('dy_mm', 0.0))
    except Exception:
        req_dx, req_dy = 0.0, 0.0

    out['omr_offsets_debug'] = {
        'raw': raw_omr_offsets,
        'requested_offsets_mm': [req_dx, req_dy],
        'applied_offsets_mm': out.get('omr_offsets_used_mm'),
        'clamp_mm': (None if clamp_mm is None else float(clamp_mm)),
        'fallback_none_ratio': (None if fallback_none_ratio is None else float(fallback_none_ratio)),
        'auto_shift_mm': [float(auto_shift_mm[0]), float(auto_shift_mm[1])] if 'auto_shift_mm' in locals() else [0.0, 0.0],
        'fiducials_present': True if fiducial_info is not None else False,
    }

    if warnings:
        out["warnings"] = warnings

    if fiducial_info is not None:
        out["fiducials"] = fiducial_info
    return out


def grade_pdf(pdf_bytes: bytes, config: Dict[str, Any], subject: Dict[str, Any] = None, dx_mm_override: Optional[float] = None, dy_mm_override: Optional[float] = None) -> Dict[str, Any]:
    """Grade a PDF and return a result dict.

    If `subject` is provided and contains a `questions` list, those questions
    are merged into the top-level `config` so keys like `omr_offsets` are
    preserved while using the provided question geometry.
    """
    images = pdf_to_images(pdf_bytes)
    pages = []
    total_correct = 0
    total_questions = 0

    # Build grading_config by preserving top-level config and injecting
    # subject-provided `questions` (and optional `omr_marks`) so that
    # settings such as `omr_offsets` remain available to the grader.
    if isinstance(config, dict):
        grading_config = dict(config)
    else:
        grading_config = {}

    if isinstance(subject, dict) and subject.get('questions'):
        grading_config['questions'] = subject.get('questions')
        if subject.get('omr_marks') is not None:
            grading_config['omr_marks'] = subject.get('omr_marks')
        # Support dynamically using offsets embedded in the provided subject
        if subject.get('omr_offsets') is not None:
            grading_config['omr_offsets'] = subject.get('omr_offsets')

    for img in images:
        page_res = analyze_image(img, grading_config, dx_mm_override=dx_mm_override, dy_mm_override=dy_mm_override)
        pages.append(page_res)
        for q in page_res.get('questions', []):
            total_questions += 1
            if q.get('correct'):
                total_correct += 1

    return {"pages": pages, "score": {"correct": total_correct, "total": total_questions}}
