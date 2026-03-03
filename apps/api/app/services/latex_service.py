"""LaTeX rendering & compilation service.

Generates professional OMR mark sheets with precise coordinate calculations.
All measurements are in millimetres (mm) relative to A4 landscape (297 × 210 mm).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()
BASE = Path(__file__).resolve().parent.parent.parent  # apps/api
TEMPLATES_DIR = BASE / "templates"
STORAGE_DIR = Path(settings.STORAGE_DIR)
GENERATED_DIR = STORAGE_DIR / "generated_pdfs"

for d in (GENERATED_DIR,):
    d.mkdir(parents=True, exist_ok=True)

# ── Page constants ──────────────────────────────────────────────
PAGE_W_MM = 297.0
PAGE_H_MM = 210.0


def latex_escape(s: Any) -> str:
    if s is None:
        return ""
    try:
        s2 = str(s)
    except Exception:
        s2 = ""
    replacements = {
        "\\": r"\textbackslash{}",
        "%": r"\%",
        "&": r"\&",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        "$": r"\$",
    }
    out = s2
    for k, v in replacements.items():
        out = out.replace(k, v)
    return out


# ─── OMR alignment marks ────────────────────────────────────────
def _generate_omr_marks_block(subject: dict) -> str:
    """Generate four corner registration marks for OMR alignment."""
    try:
        if isinstance(subject, dict):
            markgap = float(subject.get("omr_markgap_mm", 8.0))
            markrad = float(subject.get("omr_markrad_mm", 1.8))
            crosslen = float(subject.get("omr_crosslen_mm", 3.0))
        else:
            markgap, markrad, crosslen = 8.0, 1.8, 3.0
    except Exception:
        markgap, markrad, crosslen = 8.0, 1.8, 3.0

    lines = [
        "% OMR registration marks",
        "\\AddToShipoutPictureBG{%",
        "  \\begin{tikzpicture}[remember picture,overlay]",
        "    \\def\\markrad{%.2fmm}" % markrad,
        "    \\def\\crosslen{%.2fmm}" % crosslen,
        "    \\def\\markgap{%.2fmm}" % markgap,
        "",
        "    % top-left: filled dot with cross",
        "    \\coordinate (mkTL) at ($(current page.north west)+(\\markgap,-\\markgap)$);",
        "    \\fill (mkTL) circle (\\markrad);",
        "    \\draw[line width=0.6pt] (mkTL) ++(-\\crosslen,0) -- ++(2*\\crosslen,0);",
        "    \\draw[line width=0.6pt] (mkTL) ++(0,-\\crosslen) -- ++(0,2*\\crosslen);",
        "",
        "    % top-right: filled square",
        "    \\coordinate (mkTR) at ($(current page.north east)+(-\\markgap,-\\markgap)$);",
        "    \\fill ($(mkTR)+(-\\markrad,-\\markrad)$) rectangle ($(mkTR)+(\\markrad,\\markrad)$);",
        "",
        "    % bottom-left: filled triangle",
        "    \\coordinate (mkBL) at ($(current page.south west)+(\\markgap,\\markgap)$);",
        "    \\fill ($(mkBL)+(0,\\markrad)$) -- ++(-1.2*\\markrad,-1.6*\\markrad) -- ++(2.4*\\markrad,0) -- cycle;",
        "",
        "    % bottom-right: hollow ring",
        "    \\coordinate (mkBR) at ($(current page.south east)+(-\\markgap,\\markgap)$);",
        "    \\draw[line width=0.6pt] (mkBR) circle (\\markrad);",
        "    \\fill (mkBR) circle (0.5mm);",
        "  \\end{tikzpicture}%",
        "}",
    ]
    return "\n".join(lines) + "\n"


# ─── Questions TeX generator ───────────────────────────────────────
def _render_questions_tex(subject: dict) -> tuple[str, dict]:
    """Generate a TeX chunk for question bubbles.

    Supports up to 15+ choices per question by dynamically sizing bubbles
    to fit within the available column width.

    All coordinates use TikZ with (0,0) at bottom-left of the page.
    y increases upward.
    """
    try:
        qs = subject.get("questions", []) if isinstance(subject, dict) else []
    except Exception:
        qs = []

    if not qs:
        return "% No questions defined\n", {"questions": [], "bubbles": []}

    # ── Layout parameters (all in mm) ───────────────────────
    MARGIN_LEFT = 14.0
    MARGIN_RIGHT = 14.0
    MARGIN_BOTTOM = 12.0

    # Defaults — can all be overridden from subject config / layout dict
    HEADER_OFFSET = 20.0   # distance from page top to first question row
    ROW_HEIGHT = 6.0       # vertical distance between question centres
    BUBBLE_RX = 2.0        # default horizontal radius (will auto-shrink)
    BUBBLE_RY = 1.8        # default vertical radius (will auto-shrink)
    LABEL_COL_W = 10.0     # width for the question number label
    COL_GAP = 3.0          # gap between columns

    # Read overrides from subject-level "layout" dict or top-level keys
    layout = subject.get("layout", {}) if isinstance(subject, dict) else {}
    try:
        if isinstance(subject, dict):
            HEADER_OFFSET = float(layout.get("header_offset_mm", subject.get("header_offset_mm", HEADER_OFFSET)))
            ROW_HEIGHT = float(layout.get("row_height", subject.get("row_h", ROW_HEIGHT)))
            LABEL_COL_W = float(layout.get("label_width", subject.get("label_w", LABEL_COL_W)))
            BUBBLE_RX = float(layout.get("bubble_rx", subject.get("bubble_rx", BUBBLE_RX)))
            BUBBLE_RY = float(layout.get("bubble_ry", subject.get("bubble_ry", BUBBLE_RY)))
            COL_GAP = float(layout.get("col_gap", subject.get("col_gap", COL_GAP)))
    except Exception:
        pass

    # ── Compute layout ──────────────────────────────────────
    total_q = len(qs)
    usable_w = PAGE_W_MM - MARGIN_LEFT - MARGIN_RIGHT
    usable_h = PAGE_H_MM - HEADER_OFFSET - MARGIN_BOTTOM
    max_rows_per_col = max(1, int(usable_h / ROW_HEIGHT))

    desired_cols = int(layout.get("cols", subject.get("cols", 4))) if isinstance(subject, dict) else 4
    # Clamp columns to reasonable range
    desired_cols = max(1, min(desired_cols, 8))

    rows_per_col = (total_q + desired_cols - 1) // desired_cols if total_q > 0 else 1
    if rows_per_col > max_rows_per_col:
        rows_per_col = max_rows_per_col
    cols_used = (total_q + rows_per_col - 1) // rows_per_col if rows_per_col > 0 else 1

    # Column width (evenly distribute, accounting for gaps)
    total_gap = COL_GAP * max(0, cols_used - 1)
    col_w = (usable_w - total_gap) / cols_used

    # Top-Y for the first row (TikZ coords: 0 at bottom, PAGE_H at top)
    top_y = PAGE_H_MM - HEADER_OFFSET

    # ── Determine max choices across all questions for adaptive sizing ──
    max_choices = 4
    for q in qs:
        if isinstance(q, dict):
            ch = q.get("choices")
            nc = int(q.get("num_choices") or subject.get("num_choices") or 4)
            if isinstance(ch, list) and len(ch) > 0:
                nc = len(ch)
            max_choices = max(max_choices, nc)

    # ── Generate TikZ ───────────────────────────────────────
    lines = [
        "% ── Questions block (auto-generated) ──",
        "\\noindent",
        "\\begin{tikzpicture}[x=1mm,y=1mm]",
    ]

    meta: dict[str, Any] = {"bubbles": [], "questions": []}

    for col in range(cols_used):
        # Column left edge
        col_left_x = MARGIN_LEFT + col * (col_w + COL_GAP)

        # Column separator line
        if col > 0:
            sep_x = col_left_x - COL_GAP / 2.0
            lines.append(
                "  \\draw[gridLine, line width=0.3pt] (%.1f, %.1f) -- (%.1f, %.1f);"
                % (sep_x, top_y + 2, sep_x, top_y - rows_per_col * ROW_HEIGHT - 2)
            )

        for row in range(rows_per_col):
            q_idx = col * rows_per_col + row
            if q_idx >= total_q:
                continue

            q = qs[q_idx]
            global_idx = q_idx
            if isinstance(q, dict) and q.get("_global_index") is not None:
                try:
                    global_idx = int(q["_global_index"])
                except Exception:
                    global_idx = q_idx

            # Centre Y of this row
            cy = top_y - (row + 0.5) * ROW_HEIGHT
            cx_start = col_left_x

            # ── Question label ──
            qlabel = str(q.get("label") or q.get("id") or (global_idx + 1)) if isinstance(q, dict) else str(q_idx + 1)
            label_cx = cx_start + LABEL_COL_W / 2.0
            lines.append("  %% Q%d" % (global_idx + 1))

            # Label background
            lines.append(
                "  \\fill[labelBg, rounded corners=0.6mm] (%.2f, %.2f) rectangle (%.2f, %.2f);"
                % (cx_start + 0.5, cy - ROW_HEIGHT / 2.0 + 0.4,
                   cx_start + LABEL_COL_W - 0.5, cy + ROW_HEIGHT / 2.0 - 0.4)
            )
            lines.append(
                "  \\node[anchor=center, font=\\footnotesize\\bfseries] at (%.2f, %.2f) {%s};"
                % (label_cx, cy, latex_escape(qlabel))
            )

            # ── Bubble area ──
            bubble_area_start = cx_start + LABEL_COL_W + 0.5
            bubble_area_end = cx_start + col_w - 1.0

            # Horizontal guide line
            lines.append(
                "  \\draw[gridLineFaint, line width=0.2pt] (%.2f, %.2f) -- (%.2f, %.2f);"
                % (bubble_area_start, cy - ROW_HEIGHT / 2.0, bubble_area_end, cy - ROW_HEIGHT / 2.0)
            )

            # ── Determine choices ──
            choices = q.get("choices") if isinstance(q, dict) and isinstance(q.get("choices"), list) and len(q.get("choices")) > 0 else None
            if choices:
                n_choices = len(choices)
                labels_list = [
                    (c.get("label") if isinstance(c, dict) else str(i + 1))
                    for i, c in enumerate(choices)
                ]
            else:
                n_choices = int(q.get("num_choices") or subject.get("num_choices") or 4) if isinstance(q, dict) else 4
                labels_list = [str(i + 1) for i in range(n_choices)]

            # ── Adaptive bubble sizing ──
            bubble_area_w = bubble_area_end - bubble_area_start
            # Each bubble gets an equal slot
            slot_w = bubble_area_w / max(n_choices, 1)

            # Scale bubble radius to fit slot, with padding
            effective_rx = min(BUBBLE_RX, (slot_w - 0.6) / 2.0)
            effective_ry = min(BUBBLE_RY, (ROW_HEIGHT - 1.2) / 2.0)
            # Minimum readable size
            effective_rx = max(effective_rx, 1.0)
            effective_ry = max(effective_ry, 0.9)

            # Font size scales with bubble size
            if n_choices <= 6:
                font_size = "6pt"
            elif n_choices <= 10:
                font_size = "5pt"
            else:
                font_size = "4pt"

            qmeta: dict[str, Any] = {"index": global_idx, "label": qlabel, "bubbles": []}

            for j in range(n_choices):
                bx = bubble_area_start + (j + 0.5) * slot_w
                by = cy

                # Draw bubble
                lines.append(
                    "  \\draw[bubbleBorder, line width=0.6pt] (%.2f, %.2f) ellipse (%.2fmm and %.2fmm);"
                    % (bx, by, effective_rx, effective_ry)
                )
                # Label inside bubble
                lbl = labels_list[j] if j < len(labels_list) else str(j + 1)
                lines.append(
                    "  \\node[font=\\fontsize{%s}{%s}\\selectfont, black!60] at (%.2f, %.2f) {%s};"
                    % (font_size, font_size, bx, by, latex_escape(lbl))
                )

                # Metadata for OMR grading
                qmeta["bubbles"].append({
                    "bubble_index": j,
                    "x_mm": round(float(bx), 3),
                    "y_mm": round(float(by), 3),
                    "y_mm_top": round(float(PAGE_H_MM - by), 3),
                    "x_norm": round(float(bx) / PAGE_W_MM, 6),
                    "y_norm_top": round(float((PAGE_H_MM - by) / PAGE_H_MM), 6),
                    "width_mm": round(float(effective_rx * 2.0), 3),
                    "height_mm": round(float(effective_ry * 2.0), 3),
                    "w_norm": round(float((effective_rx * 2.0) / PAGE_W_MM), 6),
                    "h_norm": round(float((effective_ry * 2.0) / PAGE_H_MM), 6),
                    "label": lbl,
                })

            meta["questions"].append(qmeta)

    # Store layout metadata for debugging / OMR
    meta["layout"] = {
        "header_offset_mm": HEADER_OFFSET,
        "row_height_mm": ROW_HEIGHT,
        "cols_used": cols_used,
        "rows_per_col": rows_per_col,
        "max_choices": max_choices,
        "label_col_w": LABEL_COL_W,
    }

    lines.append("\\end{tikzpicture}")
    return "\n".join(lines), meta


def _render_questions_tex_single_block(subject: dict) -> tuple[str, dict]:
    """Render a single A4 page worth of questions, truncating if needed."""
    try:
        qs = subject.get("questions", []) if isinstance(subject, dict) else []
    except Exception:
        qs = []

    # Calculate capacity using same defaults as _render_questions_tex
    layout = subject.get("layout", {}) if isinstance(subject, dict) else {}
    HEADER_OFFSET = float(layout.get("header_offset_mm", subject.get("header_offset_mm", 20.0))) if isinstance(subject, dict) else 20.0
    MARGIN_BOTTOM = 12.0
    ROW_HEIGHT = float(layout.get("row_height", subject.get("row_h", 6.0))) if isinstance(subject, dict) else 6.0

    cols = int(layout.get("cols", subject.get("cols", 4))) if isinstance(subject, dict) else 4
    cols = max(1, min(cols, 8))
    usable_h = PAGE_H_MM - HEADER_OFFSET - MARGIN_BOTTOM
    max_rows_per_col = max(1, int(usable_h / ROW_HEIGHT))
    capacity = max_rows_per_col * max(1, cols)

    # Prepare questions with global indices
    new_qs = []
    for i, q in enumerate(qs[:capacity]):
        q2 = dict(q) if isinstance(q, dict) else {"label": str(q)}
        q2["_global_index"] = i
        new_qs.append(q2)

    subj_copy = dict(subject) if isinstance(subject, dict) else {}
    subj_copy["questions"] = new_qs
    subj_copy["cols"] = cols

    tex, meta = _render_questions_tex(subj_copy)

    if len(new_qs) < len(qs):
        note = "\n\\begin{center}\\small\\color{accentBlue} (表示: 先頭 %d / 全 %d 問)\\end{center}\n" % (len(new_qs), len(qs))
        tex = tex + note
        meta = dict(meta)
        meta["truncated"] = True
        meta["total_questions"] = len(qs)
        meta["shown_questions"] = len(new_qs)

    return tex, meta


# ─── TeX source rendering ─────────────────────────────────────────
def render_tex_source(subject: dict, cand_name: str = "", exam_number: str = "") -> tuple[bool, Any]:
    """Render the .tex source for a subject.

    Returns (True, (tex_source, questions_meta)) or (False, (errcode, logs)).
    """
    try:
        tmpl_map = {"default": "sheet.tex", "math_double": "sheet.math_double.tex"}
        tmpl_key = subject.get("sheet_template", "default") if isinstance(subject, dict) else "default"
        tmpl_file = tmpl_map.get(tmpl_key, "sheet.tex")
        tpl_path = TEMPLATES_DIR / tmpl_file

        if not tpl_path.exists():
            return False, ("template_missing", f"Template not found: {tpl_path}")

        content = tpl_path.read_text(encoding="utf-8")

        header_lines: list[str] = []
        if isinstance(subject, dict) and subject.get("name"):
            header_lines.append("\\renewcommand{\\SubjectName}{%s}" % latex_escape(subject.get("name")))
        if cand_name:
            header_lines.append("\\renewcommand{\\CandidateName}{%s}" % latex_escape(cand_name))
        if exam_number:
            header_lines.append("\\renewcommand{\\ExamNumber}{%s}" % latex_escape(exam_number))
        header = "\n".join(header_lines) + ("\n" if header_lines else "")

        try:
            if tmpl_key == "default":
                questions_tex, questions_meta = _render_questions_tex_single_block(subject)
            else:
                questions_tex, questions_meta = _render_questions_tex(subject)
        except Exception:
            questions_tex = "% No questions generated (error)"
            questions_meta = {"questions": [], "bubbles": []}

        try:
            marks = _generate_omr_marks_block(subject)
            if "\\begin{document}" in content:
                content = content.replace("\\begin{document}", "\\begin{document}\n" + marks, 1)
            else:
                content = marks + "\n" + content
            questions_meta = dict(questions_meta)
            questions_meta.setdefault("omr_marks", {})
            questions_meta["omr_marks"].update(
                {"markgap_mm": 8.0, "markrad_mm": 1.8, "crosslen_mm": 3.0, "shapes": ["dot+cross", "square", "triangle", "ring"]}
            )
        except Exception:
            pass

        # Insert header (\newcommand definitions) into preamble,
        # NOT before \documentclass (which would be invalid LaTeX).
        if header and "\\begin{document}" in content:
            content = content.replace("\\begin{document}", header + "\\begin{document}", 1)
        elif header:
            content = header + content

        if "%%QUESTIONS%%" in content:
            content = content.replace("%%QUESTIONS%%", questions_tex)
        elif "\\end{document}" in content:
            content = content.replace("\\end{document}", questions_tex + "\\end{document}")
        else:
            content = content + "\n" + questions_tex

        return True, (content, questions_meta)
    except Exception:
        import traceback
        return False, ("render_error", traceback.format_exc())


# ─── Compile LaTeX → PDF ──────────────────────────────────────────
def compile_latex_and_save(subject: dict, cand_name: str = "", exam_number: str = "") -> tuple[bool, Any]:
    """Compile LaTeX and save PDF. Returns (True, gid) or (False, (errcode, logs))."""
    ok, info = render_tex_source(subject, cand_name=cand_name, exam_number=exam_number)
    if not ok:
        return False, info
    tex, questions_meta = info

    with tempfile.TemporaryDirectory() as td:
        tex_path = os.path.join(td, "sheet.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex)

        xe_path = shutil.which("xelatex")
        if not xe_path:
            candidates = [
                "/Library/TeX/texbin/xelatex",
                "/usr/texbin/xelatex",
                "/usr/local/texlive/2025/bin/universal-darwin/xelatex",
                "/usr/local/texlive/2025/bin/x86_64-darwin/xelatex",
                "/usr/bin/xelatex",
            ]
            for p in candidates:
                if os.path.exists(p) and os.access(p, os.X_OK):
                    xe_path = p
                    break

        cmd = [xe_path or "xelatex", "-interaction=nonstopmode", "-halt-on-error", "sheet.tex"]
        try:
            import sys
            print(f"[latex] Running: {' '.join(cmd)}", file=sys.stderr, flush=True)
            proc = subprocess.run(cmd, cwd=td, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
            out = proc.stdout.decode("utf-8", errors="replace")
            err = proc.stderr.decode("utf-8", errors="replace")
            if proc.returncode != 0:
                logs = out + "\n" + err
                print(f"[latex] FAILED (rc={proc.returncode}):\n{logs[-2000:]}", file=sys.stderr, flush=True)
                return False, ("latex_failed", logs)
            pdf_path = os.path.join(td, "sheet.pdf")
            if not os.path.exists(pdf_path):
                print(f"[latex] PDF not generated:\n{(out + err)[-1000:]}", file=sys.stderr, flush=True)
                return False, ("pdf_missing", out + "\n" + err)
            print(f"[latex] OK – PDF generated", file=sys.stderr, flush=True)

            gid = uuid.uuid4().hex
            dst = GENERATED_DIR / f"{gid}.pdf"
            shutil.copyfile(pdf_path, str(dst))

            # Overlay OMR marks
            try:
                if isinstance(subject, dict) and questions_meta and questions_meta.get("omr_marks"):
                    om = questions_meta.get("omr_marks")
                    markrad = float(om.get("markrad_mm", 1.8))
                    crosslen_val = float(om.get("crosslen_mm", 3.0))
                    markgap_val = float(om.get("markgap_mm", 8.0))
                    overlay_lines = [
                        "\\documentclass[10pt]{article}",
                        "\\usepackage[a4paper,landscape,margin=0mm]{geometry}",
                        "\\usepackage{pdfpages}",
                        "\\usepackage{tikz}",
                        "\\usetikzlibrary{calc}",
                        "\\pagestyle{empty}",
                        "\\begin{document}",
                        "\\includepdf[pages=-,picturecommand={%",
                        "  \\begin{tikzpicture}[remember picture,overlay]",
                        "    \\def\\markrad{%.2fmm}" % markrad,
                        "    \\def\\crosslen{%.2fmm}" % crosslen_val,
                        "    \\def\\markgap{%.2fmm}" % markgap_val,
                        "    \\coordinate (mkTL) at ($(current page.north west)+(\\markgap,-\\markgap)$);",
                        "    \\fill (mkTL) circle (\\markrad);",
                        "    \\draw[line width=0.6pt] (mkTL) ++(-\\crosslen,0) -- ++(2*\\crosslen,0);",
                        "    \\draw[line width=0.6pt] (mkTL) ++(0,-\\crosslen) -- ++(0,2*\\crosslen);",
                        "    \\coordinate (mkTR) at ($(current page.north east)+(-\\markgap,-\\markgap)$);",
                        "    \\fill ($(mkTR)+(-\\markrad,-\\markrad)$) rectangle ($(mkTR)+(\\markrad,\\markrad)$);",
                        "    \\coordinate (mkBL) at ($(current page.south west)+(\\markgap,\\markgap)$);",
                        "    \\fill ($(mkBL)+(0,\\markrad)$) -- ++(-1.2*\\markrad,-1.6*\\markrad) -- ++(2.4*\\markrad,0) -- cycle;",
                        "    \\coordinate (mkBR) at ($(current page.south east)+(-\\markgap,\\markgap)$);",
                        "    \\draw[line width=0.6pt] (mkBR) circle (\\markrad);",
                        "    \\fill (mkBR) circle (0.5mm);",
                        "  \\end{tikzpicture}% }]{sheet.pdf}",
                        "\\end{document}",
                    ]
                    overlay_tex = os.path.join(td, "overlay.tex")
                    with open(overlay_tex, "w", encoding="utf-8") as of:
                        of.write("\n".join(overlay_lines))
                    proc2 = subprocess.run(
                        [xe_path or "xelatex", "-interaction=nonstopmode", "-halt-on-error", "overlay.tex"],
                        cwd=td, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60,
                    )
                    overlay_pdf = os.path.join(td, "overlay.pdf")
                    if proc2.returncode == 0 and os.path.exists(overlay_pdf):
                        shutil.copyfile(overlay_pdf, str(dst))
            except Exception:
                pass

            # Save metadata JSON
            meta = {
                "subject": subject.get("name") if isinstance(subject, dict) else None,
                "candidate_name": cand_name,
                "exam_number": exam_number,
                "questions_meta": questions_meta,
            }
            meta_path = GENERATED_DIR / f"{gid}.json"
            with open(meta_path, "w", encoding="utf-8") as mf:
                json.dump(meta, mf, ensure_ascii=False, indent=2)

            return True, gid
        except FileNotFoundError:
            return False, ("xelatex_not_found", "xelatex not found. PATH=" + os.environ.get("PATH", ""))
        except subprocess.TimeoutExpired:
            return False, ("timeout", "xelatex timed out")
