"""Conexão e inicialização do PostGIS."""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DEFAULT_URL = "postgresql://terraiq:terraiq@localhost:5432/terraiq"
INTERNAL_SRID = int(os.getenv("INTERNAL_SRID", "31985"))

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_engine() -> Engine:
    url = os.getenv("DATABASE_URL", DEFAULT_URL)
    # values_plus_batch: executemany de SQL textual (upsert de comps) vai em páginas via
    # execute_batch em vez de 1 round-trip por linha — contra Neon remoto, 28k linhas
    # caíam de >1h para minutos. Sem efeito em execute() simples da API.
    # pool_pre_ping: o Neon suspende o compute ocioso e fecha as conexões do pool; sem o ping
    # na retirada, o 1º request depois disso usava conexão morta → 500 ("SSL connection has
    # been closed unexpectedly"). Custa 1 round-trip por request; reconecta sozinho.
    return create_engine(
        url, future=True, executemany_mode="values_plus_batch", pool_pre_ping=True
    )


def init_db(engine: Engine | None = None) -> None:
    """Habilita PostGIS e aplica sql/schema.sql (idempotente)."""
    engine = engine or get_engine()
    schema_sql = (_PROJECT_ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")
    # psycopg2 cru: executa o script inteiro de uma vez e não interpola '%' (há '%' em comentários)
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        cur.execute(schema_sql)
        raw.commit()
    finally:
        raw.close()
    print("schema aplicado em", engine.url.render_as_string(hide_password=True))


if __name__ == "__main__":
    init_db()
