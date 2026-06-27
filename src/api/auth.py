"""Autenticação: register / login (JWT) / me. bcrypt + rate-limit + erro genérico."""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.api.db import get_conn
from src.api.schemas import RegisterIn, TokenOut, UserOut
from src.api.security import (
    convite_valido,
    cria_token,
    decodifica_token,
    hash_senha,
    registro_aberto,
    verifica_senha,
)

log = logging.getLogger("terraiq.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Rate-limit simples em memória, por IP (MVP). Em produção: Redis ou no proxy/CDN.
_HITS: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(request: Request, limit: int = 10, window: int = 900) -> None:
    ip = request.client.host if request.client else "?"
    now = time.time()
    dq = _HITS[ip]
    while dq and now - dq[0] > window:
        dq.popleft()
    if len(dq) >= limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "muitas tentativas; tente mais tarde")
    dq.append(now)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, request: Request, conn: Connection = Depends(get_conn)) -> UserOut:
    rate_limit(request)
    # Registro fechado por convite: sem env REGISTER_INVITE_CODE → ninguém se cadastra.
    if not registro_aberto():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "registro desabilitado")
    if not convite_valido(body.invite_code):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "código de convite inválido")
    exists = conn.execute(text("SELECT 1 FROM app.users WHERE email = :e"), {"e": body.email}).first()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "e-mail já cadastrado")
    row = conn.execute(
        text(
            "INSERT INTO app.users (email, senha_hash, nome) "
            "VALUES (:e, :h, :n) RETURNING id, email, nome"
        ),
        {"e": body.email, "h": hash_senha(body.senha), "n": body.nome},
    ).mappings().first()
    conn.commit()
    return UserOut(id=row["id"], email=row["email"], nome=row["nome"])


@router.post("/login", response_model=TokenOut)
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    conn: Connection = Depends(get_conn),
) -> TokenOut:
    rate_limit(request)
    row = conn.execute(
        text("SELECT id, senha_hash, ativo FROM app.users WHERE email = :e"),
        {"e": form.username},
    ).mappings().first()
    # Erro genérico: não revela se o e-mail existe.
    if row is None or not row["ativo"] or not verifica_senha(form.password, row["senha_hash"]):
        log.warning("login falhou (email=%s)", form.username)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "credenciais inválidas")
    return TokenOut(access_token=cria_token(str(row["id"])))


def get_current_user(
    token: str = Depends(oauth2), conn: Connection = Depends(get_conn)
) -> int:
    sub = decodifica_token(token)
    if sub is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "token inválido", headers={"WWW-Authenticate": "Bearer"}
        )
    row = conn.execute(text("SELECT 1 FROM app.users WHERE id = :i AND ativo"), {"i": int(sub)}).first()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "usuário inválido")
    return int(sub)


@router.get("/me", response_model=UserOut)
def me(user_id: int = Depends(get_current_user), conn: Connection = Depends(get_conn)) -> UserOut:
    row = conn.execute(
        text("SELECT id, email, nome FROM app.users WHERE id = :i"), {"i": user_id}
    ).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "não encontrado")
    return UserOut(id=row["id"], email=row["email"], nome=row["nome"])
