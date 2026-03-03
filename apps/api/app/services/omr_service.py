"""OMR grading service – thin wrapper around omr.py."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Optional

from app.config import get_settings

settings = get_settings()
STORAGE_DIR = Path(settings.STORAGE_DIR)
GENERATED_DIR = STORAGE_DIR / "generated_pdfs"


def grade_pdf_bytes(
    pdf_bytes: bytes,
    config: dict[str, Any],
    subject: dict[str, Any] | None = None,
    dx_mm_override: float | None = None,
    dy_mm_override: float | None = None,
) -> dict[str, Any]:
    """Grade a PDF from raw bytes. Delegates to omr.grade_pdf."""
    from app.omr import grade_pdf

    return grade_pdf(
        pdf_bytes,
        config,
        subject=subject,
        dx_mm_override=dx_mm_override,
        dy_mm_override=dy_mm_override,
    )


def build_subject_for_grading(
    gen_gid: str | None,
    subject: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Build the subject dict used for grading, incorporating generated metadata
    if a gen_gid is provided.

    Returns (subject_for_grading, gen_debug).
    """
    if not gen_gid:
        return subject, None

    PAGE_W_MM = 297.0
    PAGE_H_MM = 210.0

    meta_path = GENERATED_DIR / f"{gen_gid}.json"
    if not meta_path.exists():
        return subject, None

    try:
        with open(meta_path, "r", encoding="utf-8") as mf:
            gen_meta = json.load(mf)
    except Exception:
        return subject, None

    qmeta = gen_meta.get("questions_meta") or gen_meta.get("questions_meta", {})
    gm_questions: list[dict[str, Any]] = []

    try:
        for qidx, q in enumerate(qmeta.get("questions") or []):
            choices = []
            for bidx, b in enumerate(q.get("bubbles") or []):
                try:
                    x_mm = float(b.get("x_mm"))
                    y_mm = float(b.get("y_mm"))
                    w_mm = float(b.get("width_mm"))
                    h_mm = float(b.get("height_mm"))
                    y_top_mm = PAGE_H_MM - y_mm
                    nx = max(0.0, min(1.0, x_mm / PAGE_W_MM))
                    ny = max(0.0, min(1.0, y_top_mm / PAGE_H_MM))
                    nw = max(0.0, min(1.0, w_mm / PAGE_W_MM))
                    nh = max(0.0, min(1.0, h_mm / PAGE_H_MM))
                    choices.append({"x": nx, "y": ny, "w": nw, "h": nh, "label": b.get("label")})
                except Exception:
                    continue

            # Inherit correct answer from subject
            ans = None
            try:
                if subject and isinstance(subject.get("questions"), list):
                    oqs = subject["questions"]
                    if qidx < len(oqs):
                        raw_a = oqs[qidx].get("answer")
                        if raw_a is not None:
                            if isinstance(raw_a, (int, float)):
                                ai = int(raw_a)
                                if 0 <= ai < len(choices):
                                    ans = ai
                                elif 1 <= ai <= len(choices):
                                    ans = ai - 1
                            else:
                                for ci, ch in enumerate(choices):
                                    if str(ch.get("label")) == str(raw_a):
                                        ans = ci
                                        break
            except Exception:
                pass

            gm_questions.append({"label": q.get("label"), "choices": choices, "answer": ans})
    except Exception:
        return subject, None

    if not gm_questions:
        return subject, None

    subject_for_grading: dict[str, Any] = {
        "name": gen_meta.get("subject"),
        "questions": gm_questions,
    }
    try:
        om = qmeta.get("omr_marks") or gen_meta.get("questions_meta", {}).get("omr_marks")
        if om:
            subject_for_grading["omr_marks"] = dict(om)
    except Exception:
        pass

    gen_debug = {
        "gen_gid": gen_gid,
        "meta_questions": len(qmeta.get("questions") or []),
        "passed_questions": len(gm_questions),
    }
    return subject_for_grading, gen_debug
