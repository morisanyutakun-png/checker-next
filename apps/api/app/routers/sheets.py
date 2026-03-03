"""Sheets router – PDF generation, TeX download, server-side print."""

from __future__ import annotations

import shutil
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import GeneratedPdfResponse, PrintRequest, PrintResponse
from app.services.config_service import get_subject
from app.services.latex_service import compile_latex_and_save, render_tex_source, GENERATED_DIR

router = APIRouter(prefix="/api/sheets", tags=["sheets"])


@router.get("/{subject_idx}/generate", response_model=GeneratedPdfResponse)
async def generate_pdf(
    subject_idx: int,
    name: str = Query("", alias="name"),
    exam_number: str = Query("", alias="exam_number"),
    candidate_name: str = Query("", alias="candidate_name"),
    db: AsyncSession = Depends(get_db),
):
    """Generate a PDF for the subject and return its URL."""
    subject = await get_subject(db, subject_idx)
    if subject is None:
        raise HTTPException(404, "Subject not found")

    cand = name or candidate_name
    ok, info = compile_latex_and_save(subject, cand_name=cand, exam_number=exam_number)
    if not ok:
        errcode, logs = info
        return GeneratedPdfResponse(success=False, error=errcode, logs=logs)
    gid = info
    return GeneratedPdfResponse(
        success=True,
        pdf_url=f"/api/generated/{gid}/pdf",
        meta_url=f"/api/generated/{gid}/json",
    )


@router.get("/{subject_idx}/pdf")
async def sheet_pdf(
    subject_idx: int,
    name: str = Query(""),
    exam_number: str = Query(""),
    candidate_name: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """Compile and return the PDF directly."""
    subject = await get_subject(db, subject_idx)
    if subject is None:
        raise HTTPException(404, "Subject not found")
    cand = name or candidate_name
    ok, info = compile_latex_and_save(subject, cand_name=cand, exam_number=exam_number)
    if not ok:
        errcode, logs = info
        raise HTTPException(500, detail=f"LaTeX compilation failed: {errcode}")
    gid = info
    fpath = GENERATED_DIR / f"{gid}.pdf"
    return FileResponse(str(fpath), media_type="application/pdf", filename=f"sheet_{subject_idx}.pdf")


@router.get("/{subject_idx}/tex")
async def sheet_tex(
    subject_idx: int,
    name: str = Query(""),
    exam_number: str = Query(""),
    candidate_name: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """Download the .tex source."""
    subject = await get_subject(db, subject_idx)
    if subject is None:
        raise HTTPException(404, "Subject not found")
    cand = name or candidate_name
    ok, info = render_tex_source(subject, cand_name=cand, exam_number=exam_number)
    if not ok:
        errcode, logs = info
        raise HTTPException(500, detail=logs)
    tex, _meta = info
    return Response(
        content=tex,
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=sheet_{subject_idx}.tex"},
    )


@router.post("/{subject_idx}/print", response_model=PrintResponse)
async def sheet_print(
    subject_idx: int,
    body: PrintRequest,
    db: AsyncSession = Depends(get_db),
):
    """Server-side print via CUPS."""
    subject = await get_subject(db, subject_idx)
    if subject is None:
        raise HTTPException(404, "Subject not found")

    ok, info = compile_latex_and_save(subject, cand_name=body.name, exam_number=body.exam_number)
    if not ok:
        errcode, logs = info
        return PrintResponse(ok=False, msg="LaTeX compilation failed", logs=logs)

    gid = info
    pdf_path = str(GENERATED_DIR / f"{gid}.pdf")
    printer = body.printer

    lp = shutil.which("lp") or shutil.which("lpr") or "lp"
    if lp.endswith("lpr"):
        cmdp = [lp]
        if printer:
            cmdp += ["-P", printer]
        cmdp += [pdf_path]
    else:
        cmdp = [lp]
        if printer:
            cmdp += ["-d", printer]
        cmdp += ["-o", "landscape", pdf_path]

    try:
        pproc = subprocess.run(cmdp, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        pout = pproc.stdout.decode("utf-8", errors="replace")
        perr = pproc.stderr.decode("utf-8", errors="replace")
        if pproc.returncode == 0:
            return PrintResponse(ok=True, msg="印刷ジョブを送信しました", logs=pout + "\n" + perr)
        else:
            return PrintResponse(ok=False, msg="印刷コマンドに失敗しました", logs=pout + "\n" + perr)
    except Exception as e:
        return PrintResponse(ok=False, msg=f"印刷中にエラーが発生しました: {e}")
