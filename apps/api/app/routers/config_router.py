"""Config router – GET / PUT ``/api/config``."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import ConfigResponse, ConfigUpdate
from app.services.config_service import load_config, save_config

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=ConfigResponse)
async def get_config(db: AsyncSession = Depends(get_db)):
    cfg = await load_config(db)
    return cfg


@router.put("", response_model=ConfigResponse)
async def update_config(body: ConfigUpdate, db: AsyncSession = Depends(get_db)):
    await save_config(db, body.model_dump())
    cfg = await load_config(db)
    return cfg
