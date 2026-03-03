"""Configuration service – load/save config from/to PostgreSQL."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppConfig, Subject


async def load_config(db: AsyncSession) -> dict[str, Any]:
    """Return config dict compatible with the legacy config.json format."""
    # threshold
    cfg_row = (await db.execute(select(AppConfig).where(AppConfig.id == 1))).scalar_one_or_none()
    threshold = cfg_row.threshold if cfg_row else 0.35

    # subjects
    rows = (await db.execute(select(Subject).order_by(Subject.sort_order, Subject.id))).scalars().all()
    subjects = []
    for s in rows:
        subj: dict[str, Any] = {
            "id": s.id,
            "name": s.name,
            "sheet_template": s.sheet_template,
            "questions": s.questions or [],
        }
        if s.extra:
            subj.update(s.extra)
        subjects.append(subj)

    return {"threshold": threshold, "subjects": subjects}


async def save_config(db: AsyncSession, data: dict[str, Any]) -> None:
    """Persist the full config (threshold + subjects) into PostgreSQL.

    Replaces all existing subjects with the new data (full snapshot).
    """
    threshold = float(data.get("threshold", 0.35))

    # Upsert AppConfig
    cfg_row = (await db.execute(select(AppConfig).where(AppConfig.id == 1))).scalar_one_or_none()
    if cfg_row:
        cfg_row.threshold = threshold
    else:
        cfg_row = AppConfig(id=1, threshold=threshold)
        db.add(cfg_row)

    # Delete existing subjects and re-insert (simplest approach for full replacement)
    existing = (await db.execute(select(Subject))).scalars().all()
    for s in existing:
        await db.delete(s)
    await db.flush()

    for idx, subj_data in enumerate(data.get("subjects", [])):
        # Extract known columns; the rest goes into `extra`
        known_keys = {"name", "sheet_template", "questions", "id"}
        extra = {k: v for k, v in subj_data.items() if k not in known_keys}

        subj = Subject(
            name=subj_data.get("name", f"Subject {idx + 1}"),
            sort_order=idx,
            sheet_template=subj_data.get("sheet_template", "default"),
            questions=subj_data.get("questions", []),
            extra=extra,
        )
        db.add(subj)

    await db.commit()


async def get_subject(db: AsyncSession, idx: int) -> dict[str, Any] | None:
    """Return a single subject by sort_order index (0-based)."""
    rows = (await db.execute(
        select(Subject).order_by(Subject.sort_order, Subject.id)
    )).scalars().all()
    if idx < 0 or idx >= len(rows):
        return None
    s = rows[idx]
    subj: dict[str, Any] = {
        "id": s.id,
        "name": s.name,
        "sheet_template": s.sheet_template,
        "questions": s.questions or [],
    }
    if s.extra:
        subj.update(s.extra)
    return subj
