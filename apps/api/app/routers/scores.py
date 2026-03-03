"""Scores router – list and view grading results."""

from __future__ import annotations

import io
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Score
from app.schemas import ScoreEntry, ScoreDetail
from app.services.latex_service import GENERATED_DIR

router = APIRouter(prefix="/api/scores", tags=["scores"])
SCORES_DIR = GENERATED_DIR / "scores"


@router.get("", response_model=list[ScoreEntry])
async def list_scores(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Score).order_by(Score.created_at.desc())
    )).scalars().all()
    entries = []
    for s in rows:
        entries.append(ScoreEntry(
            id=str(s.id),
            subject_name=s.subject_name,
            timestamp=s.created_at.isoformat() + "Z" if s.created_at else None,
            created_at=s.created_at,
        ))
    return entries


@router.get("/{score_id}", response_model=ScoreDetail)
async def get_score(score_id: str, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(Score).where(Score.id == score_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Score not found")
    return ScoreDetail(
        id=str(row.id),
        subject_name=row.subject_name,
        result=row.result,
        gen_debug=row.gen_debug,
        created_at=row.created_at,
    )


@router.get("/{score_id}/annotated/{page_idx}")
async def score_annotated_page(score_id: str, page_idx: int, db: AsyncSession = Depends(get_db)):
    """Return annotated PNG of a page with bounding boxes overlaid."""
    row = (await db.execute(
        select(Score).where(Score.id == score_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Score not found")

    # Find PDF
    pdf_path = SCORES_DIR / f"score-{score_id}.pdf"
    if not pdf_path.exists() and row.pdf_path:
        pdf_path = Path(row.pdf_path)
    if not pdf_path.exists():
        raise HTTPException(404, "Score PDF not found")

    try:
        from app.omr import pdf_to_images
        from PIL import ImageDraw

        with open(pdf_path, "rb") as pf:
            pdf_bytes = pf.read()
        imgs = pdf_to_images(pdf_bytes)
        if page_idx < 1 or page_idx > len(imgs):
            raise HTTPException(404, "Page not found")

        img = imgs[page_idx - 1].convert("RGBA")
        draw = ImageDraw.Draw(img, "RGBA")
        result = row.result or {}
        pages = result.get("pages", [])
        if page_idx - 1 < len(pages):
            qlist = pages[page_idx - 1].get("questions", [])
            for qi, q in enumerate(qlist):
                for c in q.get("choices", []):
                    b = c.get("bbox_px") or [0, 0, 0, 0]
                    x0, y0, bw, bh = b[0], b[1], b[2], b[3]
                    x1, y1 = x0 + bw, y0 + bh
                    draw.rectangle([x0, y0, x1, y1], outline=(255, 0, 0, 200), width=2)
                    if q.get("selected_index") == c.get("index"):
                        draw.rectangle([x0, y0, x1, y1], fill=(255, 255, 0, 80))
                    if q.get("answer") is not None and c.get("index") == q.get("answer"):
                        draw.rectangle([x0, y0, x1, y1], outline=(0, 200, 0, 220), width=2)
                    lbl = f"{qi+1}-{c.get('index')} {int(c.get('score', 0)*100)}%"
                    try:
                        draw.text((x0 + 2, y0 + 2), lbl, fill=(0, 0, 0, 220))
                    except Exception:
                        pass

        bio = io.BytesIO()
        img.save(bio, format="PNG")
        bio.seek(0)
        return StreamingResponse(bio, media_type="image/png")
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(500, detail=traceback.format_exc())
