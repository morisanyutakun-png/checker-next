"""Generated-PDFs router – serve compiled PDFs and metadata."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from app.services.latex_service import GENERATED_DIR

router = APIRouter(prefix="/api/generated", tags=["generated"])


@router.get("/{gid}/pdf")
async def get_generated_pdf(gid: str):
    fpath = GENERATED_DIR / f"{gid}.pdf"
    if not fpath.exists():
        raise HTTPException(404, f"Generated PDF {gid} not found")
    return FileResponse(
        str(fpath),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="generated_{gid}.pdf"'},
    )


@router.get("/{gid}/json")
async def get_generated_meta(gid: str):
    fpath = GENERATED_DIR / f"{gid}.json"
    if not fpath.exists():
        raise HTTPException(404, f"Generated metadata {gid} not found")
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return JSONResponse(content=data)
