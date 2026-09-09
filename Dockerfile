# Multi-stage build: frontend (Node) then backend (Python + Tesseract OCR).
# Mirrors the repo layout so app/core/config.py resolves PROJECT_ROOT=/app.

# ---------- Stage 1: build the frontend ----------
FROM node:22-slim AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: python runtime ----------
FROM python:3.12-slim

# Tesseract OCR for scanned PDFs (English model included)
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Backend source
COPY backend/ /app/backend/

# Built frontend (served by FastAPI at /)
COPY --from=frontend-build /build/dist /app/frontend/dist

# Storage structure (writable at runtime)
RUN mkdir -p /app/storage/uploads /app/storage/processed \
    /app/storage/outputs /app/storage/temp /app/backend/data

ENV TESSERACT_CMD=tesseract \
    PYTHONUNBUFFERED=1

# Render injects PORT; Koyeb expects the EXPOSEd port (default 8000).
EXPOSE 8000
WORKDIR /app/backend
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/health', timeout=4)" || exit 1
CMD python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
