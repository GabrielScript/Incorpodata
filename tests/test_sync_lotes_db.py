"""Integração DB (gated): sync_lotes.aplicar preserva ids e recalcula zona/altura.

Só roda com INCORPODATA_DB_TESTS=1 e Postgres alcançável (DATABASE_URL ou dev local) com
geo.zonas carregada; caso contrário skip. Mexe só em inscrições com prefixo de teste e
limpa no fim.
"""
from __future__ import annotations

import os

import geopandas as gpd
import pytest
from shapely.geometry import MultiPolygon, box
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.getenv("INCORPODATA_DB_TESTS") != "1",
    reason="integração DB: export INCORPODATA_DB_TESTS=1 (e Postgres de pé) p/ rodar",
)

PFX = "__tsync__"
FONTE = "__teste_sync__"


@pytest.fixture()
def engine():
    from src.db.database import get_engine

    eng = get_engine()
    with eng.begin() as c:
        # Canto de uma zona real: o lote de teste cai dentro dela e ganha linha em lote_zona.
        x0, y0 = c.execute(text(
            "SELECT ST_X(p), ST_Y(p) FROM (SELECT ST_PointOnSurface(geom) p FROM geo.zonas "
            "ORDER BY ST_Area(geom) DESC LIMIT 1) z")).one()
    eng.x0, eng.y0 = float(x0), float(y0)
    yield eng
    with eng.begin() as c:
        c.execute(text("DELETE FROM geo.lotes WHERE inscricao LIKE :p"), {"p": f"{PFX}%"})
        c.execute(text("DELETE FROM geo.cadastro_sync WHERE fonte = :f"), {"f": FONTE})
        c.execute(text("DROP TABLE IF EXISTS staging.lotes_sync"))


def _gdf(eng, rows: list[tuple[str, str, float]]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"inscricao": [f"{PFX}{r[0]}" for r in rows], "tipo": [r[1] for r in rows],
         "logradouro": ["RUA TESTE"] * len(rows), "bairro": ["CENTRO"] * len(rows)},
        geometry=[MultiPolygon([box(eng.x0 + r[2], eng.y0, eng.x0 + r[2] + 10, eng.y0 + 10)]) for r in rows],
        crs=31985,
    )


def _ids(conn) -> dict[str, int]:
    rows = conn.execute(text("SELECT inscricao, id FROM geo.lotes WHERE inscricao LIKE :p"),
                        {"p": f"{PFX}%"}).all()
    return {i.removeprefix(PFX): n for i, n in rows}


def test_aplicar_preserva_ids_e_recalcula_derivados(engine):
    from src.ingest.sync_lotes import aplicar, calcular_diff

    atual = _gdf(engine, [("A", "TERRITORIAL", 0), ("B", "TERRITORIAL", 20), ("C", "PREDIAL", 40)])
    with engine.begin() as c:
        for r in atual.itertuples():
            c.execute(text(
                "INSERT INTO geo.lotes (inscricao, logradouro, tipo, bairro, geom) "
                "VALUES (:i, :l, :t, :b, ST_GeomFromText(:g, 31985))"),
                {"i": r.inscricao, "l": r.logradouro, "t": r.tipo, "b": r.bairro, "g": r.geometry.wkt})
        antes = _ids(c)

    # B vira construído e cresce; C sai do cadastro; D é novo.
    novo = _gdf(engine, [("A", "TERRITORIAL", 0), ("D", "TERRITORIAL", 60)])
    novo = gpd.GeoDataFrame(
        [*novo.itertuples(index=False)]
        + [(f"{PFX}B", "PREDIAL", "RUA TESTE", "CENTRO",
            MultiPolygon([box(engine.x0 + 20, engine.y0, engine.x0 + 35, engine.y0 + 10)]))],
        columns=[*novo.columns], geometry="geometry", crs=31985,
    )
    diff = calcular_diff(atual, novo)
    assert (diff.novos, diff.removidos, diff.alterados) == ([f"{PFX}D"], [f"{PFX}C"], [f"{PFX}B"])

    aplicar(engine, novo, diff, FONTE, forcado=False)

    with engine.connect() as c:
        depois = _ids(c)
        assert depois["A"] == antes["A"] and depois["B"] == antes["B"]  # ids estáveis
        assert "C" not in depois and "D" in depois
        tipo_b, area_b = c.execute(text("SELECT tipo, area_geom_m2 FROM geo.lotes WHERE id = :i"),
                                   {"i": depois["B"]}).one()
        assert tipo_b == "PREDIAL" and float(area_b) == pytest.approx(150.0)
        zona = dict(c.execute(text(
            "SELECT lote_id, area_lote_m2 FROM geo.lote_zona WHERE lote_id = ANY(:ids)"),
            {"ids": [depois["B"], depois["D"]]}).all())
        assert float(zona[depois["B"]]) == pytest.approx(150.0)  # recalculada c/ a área nova
        assert depois["D"] in zona
        n_restr = c.execute(text("SELECT count(*) FROM geo.lote_restricao WHERE lote_id = ANY(:ids)"),
                            {"ids": [depois["B"], depois["D"]]}).scalar()
        assert n_restr == 2
        log = c.execute(text("SELECT novos, removidos, alterados FROM geo.cadastro_sync WHERE fonte = :f"),
                        {"f": FONTE}).one()
        assert tuple(log) == (1, 1, 1)
        assert c.execute(text("SELECT to_regclass('staging.lotes_sync')")).scalar() is None
