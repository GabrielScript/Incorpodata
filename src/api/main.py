"""Entrada da API IncorpoData.

Rodar (na raiz do projeto, com o PostGIS no ar):
    uvicorn src.api.main:app --reload
Docs interativas: http://localhost:8000/docs
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.auth import router as auth_router
from src.api.landbank import router as landbank_router
from src.api.lots import router as lots_router

app = FastAPI(title="IncorpoData API", version="0.1.0")

# CORS: em dev libera o Vite (5173); em prod o front é servido pela própria API (mesma
# origem) → CORS_ORIGINS pode ficar vazio. Lista extra via env (separada por vírgula).
_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
_origins += [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


app.include_router(lots_router)
app.include_router(auth_router)
app.include_router(landbank_router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# Frontend buildado (container único no Cloud Run). Montado por último p/ não capturar /api.
# Caminho via FRONTEND_DIST; default = frontend/dist na raiz do projeto.
_dist = Path(os.getenv("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
