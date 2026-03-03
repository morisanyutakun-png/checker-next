"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import engine, Base
from app.routers import config_router, sheets, generated, upload, scores

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create tables on startup (dev convenience); dispose engine on shutdown."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="OMR Checker API",
    version="2.0.0",
    description="OMR (Optical Mark Recognition) grading system – FastAPI backend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(config_router.router)
app.include_router(sheets.router)
app.include_router(generated.router)
app.include_router(upload.router)
app.include_router(scores.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
