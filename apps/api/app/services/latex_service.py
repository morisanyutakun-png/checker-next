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

    Layout strategy:
    ┌──────────────────────────────────────────────────────────┐
    │  HEADER (already rendered by template)  ~25mm from top  │
    │──────────────────────────────────────────────────────────│
    │  Col 1          Col 2          Col 3          Col 4     │
    │  Q1 ①②③④⑤   Q11 ①②③④⑤  Q21 ①②③④⑤  Q31 ①②③④⑤ │
    │  Q2 ①②③④⑤   Q12 ①②③④⑤  Q22 ①②③④⑤  Q32 ①②③④⑤ │
    │  ...            ...            ...            ...       │
    │  Q10 ①②③④⑤  Q20 ①②③④⑤  Q30 ①②③④⑤  Q40 ①②③④⑤ │
    └──────────────────────────────────────────────────────────┘

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
    # Margins from page edges
    MARGIN_LEFT = 14.0
    MARGIN_RIGHT = 14.0
    MARGIN_BOTTOM = 14.0

    # Top of the question area (distance from TOP of page)
    # Header is ~18mm, then 1mm gap → questions start at 22mm from top
    HEADER_OFFSET = 22.0

    # Row spacing
    ROW_HEIGHT = 7.0      # vertical distance between question centres
    BUBBLE_RX = 2.2       # horizontal radius of each bubble ellipse
    BUBBLE_RY = 2.0       # vertical radius of each bubble ellipse

    # Label column
    LABEL_COL_W = 12.0    # width for the question number label

    # Overrides from subject config
    try:
        if isinstance(subject, dict):
            ROW_HEIGHT = float(subject.get("row_h", ROW_HEIGHT))
            LABEL_COL_W = float(subject.get("label_w", LABEL_COL_W))
            BUBBLE_RX = float(subject.get("bubble_rx", BUBBLE_RX))
            BUBBLE_RY = float(subject.get("bubble_ry", BUBBLE_RY))
            HEADER_OFFSET = float(subject.get("header_offset_mm", HEADER_OFFSET))
    except Exception:
        pass

    # ── Compute layout ──────────────────────────────────────
    total_q = len(qs)
    usable_w = PAGE_W_MM - MARGIN_LEFT - MARGIN_RIGHT
    usable_h = PAGE_H_MM - HEADER_OFFSET - MARGIN_BOTTOM
    max_rows_per_col = max(1, int(usable_h / ROW_HEIGHT))

    # Try to fit in 4 cols, fall back to more if needed
    desired_cols = int(subject.get("cols", 4)) if isinstance(subject, dict) else 4
    rows_per_col = (total_q + desired_cols - 1) // desired_cols if total_q > 0 else 1
    if rows_per_col > max_rows_per_col:
        rows_per_col = max_rows_per_col
    cols_used = (total_q + rows_per_col - 1) // rows_per_col if rows_per_col > 0 else 1

    # Column spacing (evenly distribute across usable width)
    col_w = usable_w / cols_used

    # Top-Y for the first row (TikZ coords: 0 at bottom, PAGE_H at top)
    top_y = PAGE_H_MM - HEADER_OFFSET

    # ── Generate TikZ ───────────────────────────────────────
    lines = [
        "% ── Questions block (auto-generated) ──",
        "\\noindent",
        "\\begin{tikzpicture}[x=1mm,y=1mm]",
    ]

    meta: dict[str, Any] = {"bubbles": [], "questions": []}

    for col in range(cols_used):
        # Column separator line
        col_left_x = MARGIN_LEFT + col * col_w
        if col > 0:
            lines.append(
                "  \\draw[gridLine, line width=0.3pt] (%.1f, %.1f) -- (%.1f, %.1f);"
                % (col_left_x - 2, top_y + 2, col_left_x - 2, top_y - rows_per_col * ROW_HEIGHT - 2)
            )

        for row in range(rows_per_col):
            q_idx = col * rows_per_col + row
            if q_idx >= total_q:
                continue

            q = qs[q_idx]
            # Global index for metadata
            global_idx = q_idx
            if isinstance(q, dict) and q.get("_global_index") is not None:
                try:
                    global_idx = int(q["_global_index"])
                except Exception:
                    global_idx = q_idx

            # Centre Y of this row
            cy = top_y - (row + 0.5) * ROW_HEIGHT
            # Left edge of this column
            cx_start = col_left_x

            # ── Question label ──
            qlabel = str(q.get("label") or q.get("id") or (global_idx + 1)) if isinstance(q, dict) else str(q_idx + 1)
            label_cx = cx_start + LABEL_COL_W / 2.0
            lines.append("  %% Q%d" % (global_idx + 1))

            # Label background
            lines.append(
                "  \\fill[labelBg, rounded corners=0.8mm] (%.2f, %.2f) rectangle (%.2f, %.2f);"
                % (cx_start + 1, cy - ROW_HEIGHT / 2.0 + 0.6,
                   cx_start + LABEL_COL_W - 1, cy + ROW_HEIGHT / 2.0 - 0.6)
            )
            lines.append(
                "  \\node[anchor=center, font=\\small\\bfseries] at (%.2f, %.2f) {%s};"
                % (label_cx, cy, latex_escape(qlabel))
            )

            # ── Horizontal guide line ──
            bubble_area_start = cx_start + LABEL_COL_W + 1
            bubble_area_end = cx_start + col_w - 4
            lines.append(
                "  \\draw[gridLineFaint, line width=0.2pt] (%.2f, %.2f) -- (%.2f, %.2f);"
                % (bubble_area_start, cy - ROW_HEIGHT / 2.0, bubble_area_end, cy - ROW_HEIGHT / 2.0)
            )

            # ── Bubbles ──
            # Determine number of choices
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

            qmeta: dict[str, Any] = {"index": global_idx, "label": qlabel, "bubbles": []}

            # Dynamically compute bubble gap based on available width and number of choices
            bubble_area_w = bubble_area_end - bubble_area_start
            BUBBLE_GAP = bubble_area_w / max(n_choices, 1)
            # Clamp minimum gap so bubbles don't overlap
            min_gap = BUBBLE_RX * 2.2
            if BUBBLE_GAP < min_gap:
                BUBBLE_GAP = min_gap

            for j in range(n_choices):
                bx = bubble_area_start + j * BUBBLE_GAP + BUBBLE_GAP / 2.0
                by = cy

                # Stop if bubble would go outside column
                if bx + BUBBLE_RX > bubble_area_end + 1:
                    break

                # Draw bubble
                lines.append(
                    "  \\draw[bubbleBorder, line width=0.8pt] (%.2f, %.2f) ellipse (%.2fmm and %.2fmm);"
                    % (bx, by, BUBBLE_RX, BUBBLE_RY)
                )
                # Label inside bubble
                lbl = labels_list[j] if j < len(labels_list) else str(j + 1)
                lines.append(
                    "  \\node[font=\\fontsize{6pt}{6pt}\\selectfont, black!55] at (%.2f, %.2f) {%s};"
                    % (bx, by, latex_escape(lbl))
                )

                # Metadata for OMR grading
                qmeta["bubbles"].append({
                    "bubble_index": j,
                    "x_mm": round(float(bx), 3),
                    "y_mm": round(float(by), 3),
                    "y_mm_top": round(float(PAGE_H_MM - by), 3),
                    "x_norm": round(float(bx) / PAGE_W_MM, 6),
                    "y_norm_top": round(float((PAGE_H_MM - by) / PAGE_H_MM), 6),
                    "width_mm": round(float(BUBBLE_RX * 2.0), 3),
                    "height_mm": round(float(BUBBLE_RY * 2.0), 3),
                    "w_norm": round(float((BUBBLE_RX * 2.0) / PAGE_W_MM), 6),
                    "h_norm": round(float((BUBBLE_RY * 2.0) / PAGE_H_MM), 6),
                    "label": lbl,
                })

            meta["questions"].append(qmeta)

    lines.append("\\end{tikzpicture}")
    return "\n".join(lines), meta


def _render_questions_tex_single_block(subject: dict) -> tuple[str, dict]:
    """Render a single A4 page worth of questions, truncating if needed."""
    try:
        qs = subject.get("questions", []) if isinstance(subject, dict) else []
    except Exception:
        qs = []

    # Calculate capacity
    HEADER_OFFSET = 22.0
    MARGIN_BOTTOM = 14.0
    ROW_HEIGHT = 7.0
    try:
        if isinstance(subject, dict):
            ROW_HEIGHT = float(subject.get("row_h", ROW_HEIGHT))
            HEADER_OFFSET = float(subject.get("header_offset_mm", HEADER_OFFSET))
    except Exception:
        pass

    cols = int(subject.get("cols", 4)) if isinstance(subject, dict) else 4
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
