# ═══════════════════════════════════════════════════════════════
# FastAPI (OMR Checker API)  –  Root Dockerfile for deployment
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

COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: production ──────────────────────────────────────
FROM base AS prod

COPY apps/api/ .

RUN mkdir -p /app/storage/generated_pdfs/scores

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8000}/api/health')" || exit 1

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
