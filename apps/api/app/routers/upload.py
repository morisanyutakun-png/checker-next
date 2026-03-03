"""Upload router – PDF grading endpoint."""

from __future__ import annotations

import csv
import io
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import UploadResponse
from app.services.config_service import load_config, get_subject
from app.services.omr_service import grade_pdf_bytes, build_subject_for_grading
from app.services.latex_service import GENERATED_DIR
from app.models import Score

router = APIRouter(prefix="/api", tags=["upload"])

SCORES_DIR = GENERATED_DIR / "scores"
SCORES_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(
    pdf: UploadFile = File(...),
    subject_idx: int = Form(None),
    generated_gid: str = Form(""),
    generated_gid_manual: str = Form(""),
    dx_mm: str = Form(""),
    dy_mm: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Upload a scanned PDF for OMR grading."""
    data = await pdf.read()
    config = await load_config(db)

    # Determine subject
    subject = None
    if subject_idx is not None:
        subject = await get_subject(db, subject_idx)

    # Determine gen_gid
    gen_gid = (generated_gid.strip() or generated_gid_manual.strip()) or None

    # Build grading subject (incorporates generated metadata)
    subject_for_grading, gen_debug = build_subject_for_grading(gen_gid, subject)

    # Parse manual offsets
    dx_override = None
    dy_override = None
    try:
        if dx_mm.strip():
            dx_override = float(dx_mm.strip())
        if dy_mm.strip():
            dy_override = float(dy_mm.strip())
    except Exception:
        pass

    # Grade
    result = grade_pdf_bytes(
        data, config,
        subject=subject_for_grading,
        dx_mm_override=dx_override,
        dy_mm_override=dy_override,
    )

    # Build CSV
    csv_io = io.StringIO()
    writer = csv.writer(csv_io)
    writer.writerow(["page", "question", "selected", "score", "correct"])
    for pidx, page in enumerate(result["pages"], start=1):
        for q in page["questions"]:
            writer.writerow([
                pidx,
                q.get("label") or q.get("id"),
                q.get("selected_index"),
                q.get("selected_score"),
                q.get("correct"),
            ])
    csv_io.seek(0)

    # Save score to DB
    score_id = uuid.uuid4()
    subj_name = subject.get("name") if isinstance(subject, dict) else None
    score = Score(
        id=score_id,
        subject_name=subj_name,
        result=result,
        gen_debug=gen_debug,
    )
    db.add(score)

    # Also save uploaded PDF to disk
    try:
        pdf_path = SCORES_DIR / f"score-{score_id}.pdf"
        with open(pdf_path, "wb") as pf:
            pf.write(data)
        score.pdf_path = str(pdf_path)
    except Exception:
        pass

    await db.commit()

    return UploadResponse(
        result=result,
        csv_data=csv_io.getvalue(),
        subject=subj_name,
        saved_score_id=str(score_id),
        gen_debug=gen_debug,
    )
