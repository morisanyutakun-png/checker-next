# ═══════════════════════════════════════════════════════════════
# FastAPI (OMR Checker API)  –  multi-stage Dockerfile
# ═══════════════════════════════════════════════════════════════

# ── Stage 1: base ──────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgl1 \
    libglib2.0-0 \
    texlive-xetex \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    texlive-latex-extra \
    texlive-lang-japanese \
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
    poppler-utils \
    cups-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: development ──────────────────────────────────────
FROM base AS dev

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Stage 3: production ──────────────────────────────────────
FROM base AS prod

COPY . .

# Run Alembic migrations on start, then uvicorn
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
