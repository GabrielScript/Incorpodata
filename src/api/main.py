"""Entrada da API TerraIQ.

Rodar (na raiz do projeto, com o PostGIS no ar):
    uvicorn src.api.main:app --reload
Docs interativas: http://localhost:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from src.api.auth import router as auth_router
from src.api.landbank import router as landbank_router
from src.api.lots import router as lots_router

app = FastAPI(title="TerraIQ API", version="0.1.0")

# Dev: libera o Vite (5173). Em produção, restringir à origem real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
