"""Dependência de conexão para a API (reusa o engine do projeto)."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.engine import Connection, Engine

from src.db.database import get_engine

_engine: Engine | None = None


def engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = get_engine()
    return _engine


def get_conn() -> Iterator[Connection]:
    """FastAPI dependency: cede uma conexão e fecha ao fim do request."""
    with engine().connect() as conn:
        yield conn
