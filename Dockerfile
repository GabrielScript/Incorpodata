# ───────── build do frontend (Vite/React) ─────────
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/ ./
RUN npm install && npm run build

# ───────── runtime da API (FastAPI + frontend estático) ─────────
FROM python:3.12-slim AS api
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FRONTEND_DIST=/app/frontend/dist
WORKDIR /app

COPY requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt

COPY src/ ./src/
COPY sql/ ./sql/
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY --from=web /web/dist ./frontend/dist

# Cloud Run injeta $PORT (default 8080). Shell form p/ expandir a variável.
EXPOSE 8080
CMD exec uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8080}
