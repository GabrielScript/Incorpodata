"""Alertas de lote vago: regra (viability) e medição contra as camadas (alertas_lotes)."""
import geopandas as gpd
import pytest
from shapely.geometry import LineString, box

from src.api.viability import ALERTA_AGUA_PCT, ALERTA_EDIFICADO_PCT, avisos_alerta, tem_alerta
from src.ingest.alertas_lotes import EDIFICACAO_MIN_M2, calcular_alertas

SRID = 31985


def _g(geoms, **cols) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(cols, geometry=list(geoms), crs=SRID)


# ───────── regra ─────────
def test_sem_sinal_nao_alerta():
    assert tem_alerta(0, 0, False) is False
    assert tem_alerta(None, None, None) is False  # lote sem linha em geo.lote_alerta
    assert avisos_alerta(None, None, None, None) == []


def test_limiares_sao_estritos():
    assert tem_alerta(ALERTA_EDIFICADO_PCT, 0, False) is False
    assert tem_alerta(ALERTA_EDIFICADO_PCT + 0.1, 0, False) is True
    assert tem_alerta(0, ALERTA_AGUA_PCT + 0.1, False) is True
    assert tem_alerta(0, 0, True) is True


def test_aviso_de_construcao_diz_quanto_e_manda_conferir():
    (aviso,) = avisos_alerta(62.4, 2, 0, False)
    assert "62%" in aviso and "2 edificações" in aviso and "cadastro diga vago" in aviso
    assert "1 edificação)" in avisos_alerta(80, 1, 0, False)[0]


def test_avisos_acumulam_na_ordem_construcao_agua_rio():
    avisos = avisos_alerta(40, 3, 70, True)
    assert len(avisos) == 3
    assert avisos[0].startswith("Possível construção")
    assert "70% do lote fica dentro de rio" in avisos[1]
    assert "atravessa o lote" in avisos[2]


# ───────── medição ─────────
def test_calcular_alertas_mede_edificacao_agua_e_rio():
    vagos = _g([box(0, 0, 20, 20), box(100, 0, 120, 20), box(200, 0, 220, 20)], id=[1, 2, 3])
    assert EDIFICACAO_MIN_M2 > 4
    edif = _g([
        box(0, 0, 10, 20),                  # metade do lote 1
        box(15, 15, 17, 17),                # 4 m²: abaixo do mínimo, ignorada
        box(18, 0, 26, 20),                 # casa do vizinho invadindo 2 m: conta a área, não a casa
    ])
    agua = _g([box(100, 0, 110, 20), box(100, 0, 105, 20)])  # sobrepostas: não conta em dobro
    rios = _g([LineString([(210, -10), (210, 30)])])

    al = calcular_alertas(vagos, edif, agua, rios).set_index("lote_id")
    assert al.loc[1, "pct_edificado"] == pytest.approx(60.0)  # (200 + 40) / 400
    assert al.loc[1, "n_edificacoes"] == 1  # a do vizinho tem o ponto interno fora do lote
    assert al.loc[2, "pct_agua"] == pytest.approx(50.0)
    assert al.loc[1, "pct_agua"] == 0 and al.loc[2, "pct_edificado"] == 0
    assert bool(al.loc[3, "corta_rio"]) and not al.loc[[1, 2], "corta_rio"].any()


def test_calcular_alertas_limita_a_100_com_footprint_duplicado():
    vagos = _g([box(0, 0, 10, 10)], id=[7])
    edif = _g([box(0, 0, 10, 10), box(0, 0, 10, 10)])  # mesma edificação desenhada 2×
    longe = _g([box(500, 500, 501, 501)]), _g([LineString([(900, 0), (901, 0)])])
    al = calcular_alertas(vagos, edif, *longe)
    assert al["pct_edificado"].iloc[0] == 100.0
    assert al["pct_agua"].iloc[0] == 0 and not al["corta_rio"].iloc[0]
