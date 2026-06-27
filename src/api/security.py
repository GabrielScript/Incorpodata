"""Segurança: hash de senha (bcrypt) e JWT. Segredo via env, nunca no código."""
from __future__ import annotations

import hmac
import os
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

JWT_SECRET = os.getenv("JWT_SECRET", "dev-inseguro-troque-em-producao")
JWT_ALG = "HS256"
ACCESS_MIN = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))


def hash_senha(plain: str) -> str:
    return _pwd.hash(plain)


def verifica_senha(plain: str, hashed: str) -> bool:
    try:
        return _pwd.verify(plain, hashed)
    except ValueError:
        return False


def cria_token(sub: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": sub, "iat": now, "exp": now + timedelta(minutes=ACCESS_MIN)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decodifica_token(token: str) -> str | None:
    """Retorna o `sub` (id do usuário) ou None se inválido/expirado/adulterado."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError:
        return None
    sub = payload.get("sub")
    return str(sub) if sub is not None else None


# ───────── registro por convite (fecha o auto-cadastro) ─────────
def _invite_codes() -> set[str]:
    """Códigos de convite válidos. Env REGISTER_INVITE_CODE, separados por vírgula
    (permite emitir/rotacionar códigos por cliente). Lido em tempo de chamada."""
    raw = os.getenv("REGISTER_INVITE_CODE", "")
    return {c.strip() for c in raw.split(",") if c.strip()}


def registro_aberto() -> bool:
    """Registro só é permitido se houver ao menos um código configurado.
    Sem env (ou vazio) → registro FECHADO (default seguro)."""
    return bool(_invite_codes())


def convite_valido(code: str | None) -> bool:
    """True se `code` casa (comparação em tempo constante) com algum código configurado."""
    codes = _invite_codes()
    if not codes or not code:
        return False
    code = code.strip()
    return any(hmac.compare_digest(code, c) for c in codes)
