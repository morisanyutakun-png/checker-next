"""SQLAlchemy ORM models for the OMR Checker database."""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, Float, Integer, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db import Base


class AppConfig(Base):
    __tablename__ = "app_config"

    id = Column(Integer, primary_key=True, default=1)
    threshold = Column(Float, nullable=False, default=0.35)
    extra = Column(JSONB, nullable=False, default=dict)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    sheet_template = Column(String(50), nullable=False, default="default")
    questions = Column(JSONB, nullable=False, default=list)
    extra = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class GeneratedPdf(Base):
    __tablename__ = "generated_pdfs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_name = Column(String(255), nullable=True)
    candidate_name = Column(String(255), default="")
    exam_number = Column(String(50), default="")
    questions_meta = Column(JSONB, nullable=False, default=dict)
    pdf_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=func.now())


class Score(Base):
    __tablename__ = "scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_name = Column(String(255), nullable=True)
    result = Column(JSONB, nullable=False, default=dict)
    gen_debug = Column(JSONB, nullable=True)
    pdf_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=func.now())
