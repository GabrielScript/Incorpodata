"""Integração DB (gated): precedência de geo_fonte no upsert de load_comps.

Só roda com INCORPODATA_DB_TESTS=1 e Postgres alcançável (DATABASE_URL ou dev
local); caso contrário skip — a suíte padrão continua 100% offline.

Contexto: em prod (16/07) linhas pré-migração tinham geom com geo_fonte NULL;
o predicado de precedência do upsert avaliava NULL (lógica trivalente) quando a
linha nova era 'fonte_aprox' e o rótulo não era aplicado — depois o passo de
legados do geocode_comps carimbava tudo como 'fonte'.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.getenv("INCORPODATA_DB_TESTS") != "1",
    reason="integração DB: export INCORPODATA_DB_TESTS=1 (e Postgres de pé) p/ rodar",
)

SRC = "__test_take__"


def _row(source_id: str, **kw) -> dict:
    base = dict(
        source=SRC, source_id=source_id, tipo="Apartamento", business="SALE",
        preco=100000.0, area_m2=50.0, quartos=2, vagas=1,
        bairro="Bancários", endereco=None, lat=-7.19, lon=-34.87,
        loc_aproximada=False,
    )
    base.update(kw)
    return base


_SEED = text(
    """
    INSERT INTO market.comps
      (source, source_id, tipo, business, preco, area_m2, bairro, lat, lon, geom, geo_fonte)
    VALUES
      (:source, :source_id, 'Apartamento', 'SALE', 100000, 50, 'Bancários', :lat, :lon,
       ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 31985), :geo_fonte)
    """
)

_GET = text(
    "SELECT geo_fonte, lat FROM market.comps WHERE source = :s AND source_id = :sid"
)


@pytest.fixture()
def conn():
    from src.db.database import get_engine

    c = get_engine().connect()
    tx = c.begin()
    try:
        yield c
    finally:
        tx.rollback()
        c.close()


def test_reload_fonte_aprox_rotula_linha_legada_sem_geo_fonte(conn):
    # linha pré-migração: geom presente, geo_fonte NULL (estado real de prod)
    conn.execute(_SEED, {"source": SRC, "source_id": "1", "lat": -7.10, "lon": -34.80, "geo_fonte": None})

    from src.scrapers.load_comps import _UPSERT

    conn.execute(_UPSERT, [_row("1", loc_aproximada=True)])
    got = conn.execute(_GET, {"s": SRC, "sid": "1"}).one()
    assert got.geo_fonte == "fonte_aprox"  # NULL AND true → NULL: rótulo não era aplicado


def test_nominatim_resiste_a_reload_com_pino_aproximado(conn):
    conn.execute(_SEED, {"source": SRC, "source_id": "2", "lat": -7.10, "lon": -34.80, "geo_fonte": "nominatim"})

    from src.scrapers.load_comps import _UPSERT

    conn.execute(_UPSERT, [_row("2", loc_aproximada=True, lat=-7.19, lon=-34.87)])
    got = conn.execute(_GET, {"s": SRC, "sid": "2"}).one()
    assert got.geo_fonte == "nominatim"  # rua geocodificada vence pino de portal
    assert float(got.lat) == -7.10  # coordenada promovida preservada


def test_fonte_exata_do_portal_vence_nominatim(conn):
    conn.execute(_SEED, {"source": SRC, "source_id": "3", "lat": -7.10, "lon": -34.80, "geo_fonte": "nominatim"})

    from src.scrapers.load_comps import _UPSERT

    conn.execute(_UPSERT, [_row("3", loc_aproximada=False, lat=-7.19, lon=-34.87)])
    got = conn.execute(_GET, {"s": SRC, "sid": "3"}).one()
    assert got.geo_fonte == "fonte"
    assert float(got.lat) == -7.19
