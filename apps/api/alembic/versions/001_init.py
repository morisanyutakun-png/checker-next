"""Initial schema

Revision ID: 001
Revises: None
Create Date: 2026-03-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_config",
        sa.Column("id", sa.Integer, primary_key=True, default=1),
        sa.Column("threshold", sa.Float, nullable=False, server_default="0.35"),
        sa.Column("extra", JSONB, nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "subjects",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sheet_template", sa.String(50), nullable=False, server_default="'default'"),
        sa.Column("questions", JSONB, nullable=False, server_default="'[]'"),
        sa.Column("extra", JSONB, nullable=False, server_default="'{}'"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "generated_pdfs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("subject_name", sa.String(255), nullable=True),
        sa.Column("candidate_name", sa.String(255), server_default="''"),
        sa.Column("exam_number", sa.String(50), server_default="''"),
        sa.Column("questions_meta", JSONB, nullable=False, server_default="'{}'"),
        sa.Column("pdf_path", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "scores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("subject_name", sa.String(255), nullable=True),
        sa.Column("result", JSONB, nullable=False, server_default="'{}'"),
        sa.Column("gen_debug", JSONB, nullable=True),
        sa.Column("pdf_path", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("scores")
    op.drop_table("generated_pdfs")
    op.drop_table("subjects")
    op.drop_table("app_config")
