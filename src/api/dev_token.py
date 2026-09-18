"""Gera um JWT de DEV (garante um usuário dev) para usar o Landbank sem UI de login.

    python -m src.api.dev_token

Cole o token no navegador, na aba do app (DevTools → Console):
    localStorage.setItem('incorpodata_token', '<TOKEN>')

Ou em frontend/.env.local antes do `npm run dev`:
    VITE_DEV_TOKEN=<TOKEN>

Temporário: a UI de login/registro entra depois (o backend de auth já existe).
"""
from __future__ import annotations

from sqlalchemy import text

from src.api.security import cria_token, hash_senha
from src.db.database import get_engine

DEV_EMAIL = "dev@incorpodata.local"
DEV_SENHA = "dev-incorpodata"


def ensure_dev_user() -> int:
    """Cria (ou recupera) o usuário de dev e devolve o id."""
    eng = get_engine()
    with eng.begin() as conn:
        row = conn.execute(text("SELECT id FROM app.users WHERE email = :e"), {"e": DEV_EMAIL}).first()
        if row is None:
            # Dev nasce 'enterprise' → exercita VGV/PDF/landbank sem esbarrar no gate de plano.
            row = conn.execute(
                text(
                    "INSERT INTO app.users (email, senha_hash, nome, plano) "
                    "VALUES (:e, :h, :n, 'enterprise') RETURNING id"
                ),
                {"e": DEV_EMAIL, "h": hash_senha(DEV_SENHA), "n": "Dev IncorpoData"},
            ).first()
        return int(row[0])


def main() -> int:
    uid = ensure_dev_user()
    token = cria_token(str(uid))
    print(f"user_id: {uid}")
    print(f"TOKEN:\n{token}\n")
    print("No console do navegador (aba do app):")
    print(f"  localStorage.setItem('incorpodata_token', '{token}')")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
