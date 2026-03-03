"""Pydantic v2 schemas for API request / response validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


# ── Subject ────────────────────────────────────────────────────

class SubjectSchema(BaseModel):
    id: Optional[int] = None
    name: str = ""
    sort_order: int = 0
    sheet_template: str = "default"
    questions: list[dict[str, Any]] = []
    extra: dict[str, Any] = {}

    model_config = {"from_attributes": True}


# ── Config ─────────────────────────────────────────────────────

class ConfigResponse(BaseModel):
    threshold: float = 0.35
    subjects: list[SubjectSchema] = []

    model_config = {"from_attributes": True}


class ConfigUpdate(BaseModel):
    threshold: float = 0.35
    subjects: list[SubjectSchema] = []


# ── Generated PDF ──────────────────────────────────────────────

class GeneratedPdfResponse(BaseModel):
    success: bool
    pdf_url: Optional[str] = None
    meta_url: Optional[str] = None
    error: Optional[str] = None
    logs: Optional[str] = None


class GeneratedPdfMeta(BaseModel):
    id: str
    subject_name: Optional[str] = None
    candidate_name: str = ""
    exam_number: str = ""
    questions_meta: dict[str, Any] = {}
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Score ──────────────────────────────────────────────────────

class ScoreEntry(BaseModel):
    id: str
    subject_name: Optional[str] = None
    timestamp: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ScoreDetail(BaseModel):
    id: str
    subject_name: Optional[str] = None
    result: dict[str, Any] = {}
    gen_debug: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Upload ─────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    result: dict[str, Any]
    csv_data: str
    subject: Optional[str] = None
    saved_score_id: Optional[str] = None
    gen_debug: Optional[dict[str, Any]] = None


# ── Print ──────────────────────────────────────────────────────

class PrintRequest(BaseModel):
    name: str = ""
    exam_number: str = ""
    printer: Optional[str] = None


class PrintResponse(BaseModel):
    ok: bool
    msg: str = ""
    logs: Optional[str] = None
