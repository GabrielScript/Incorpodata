"""Testes da lógica pura do sync do cadastro (sem DB)."""
import geopandas as gpd
import pytest
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon, box

from src.ingest.sync_lotes import (
    REMOVIDOS_MAX,
    VARIACAO_TOTAL_MAX,
    atribuir_bairro,
    calcular_diff,
    normalizar,
    resumo,
    validar,
)

SRID = 31985


def _lotes(rows: list[tuple[str, str, float]], **extra) -> gpd.GeoDataFrame:
    """rows = (inscricao, tipo, x0): lote quadrado de 20×20 m começando em x0."""
    return gpd.GeoDataFrame(
        {
            "inscricao": [r[0] for r in rows],
            "tipo": [r[1] for r in rows],
            "logradouro": extra.get("logradouro", ["RUA A"] * len(rows)),
            "bairro": extra.get("bairro", ["CENTRO"] * len(rows)),
        },
        geometry=[MultiPolygon([box(r[2], 0, r[2] + 20, 20)]) for r in rows],
        crs=SRID,
    )


def test_normalizar_mapeia_colunas_do_filipeia_e_limpa():
    bruto = gpd.GeoDataFrame(
        {
            "CODI_CART": ["011450183", " 011450184 ", None],
            "DESC_LOGR": ["TERTULIANO CASTRO", "", "X"],
            "TIPO_IMOVE": ["territorial", "PREDIAL", "PREDIAL"],
        },
        geometry=[box(0, 0, 10, 10), box(10, 0, 20, 10), box(20, 0, 30, 10)],
        crs=SRID,
    )
    out = normalizar(bruto)
    assert list(out["inscricao"]) == ["011450183", "011450184"]  # sem inscrição cai fora
    assert list(out["tipo"]) == ["TERRITORIAL", "PREDIAL"]
    assert out["logradouro"].isna().tolist() == [False, True]  # "" vira nulo
    assert set(out.geom_type) == {"MultiPolygon"}


def test_normalizar_descarta_pedaco_nao_poligonal_do_make_valid():
    col = GeometryCollection([box(0, 0, 10, 10), LineString([(0, 0), (50, 50)])])
    bruto = gpd.GeoDataFrame(
        {"CODI_CART": ["1"], "DESC_LOGR": ["R"], "TIPO_IMOVE": ["PREDIAL"]}, geometry=[col], crs=SRID
    )
    out = normalizar(bruto)
    assert out.geom_type.tolist() == ["MultiPolygon"]
    assert out.area.iloc[0] == pytest.approx(100.0)


def test_normalizar_exige_colunas_e_crs():
    sem_col = gpd.GeoDataFrame({"CODI_CART": ["1"]}, geometry=[box(0, 0, 1, 1)], crs=SRID)
    with pytest.raises(ValueError, match="desc_logr"):
        normalizar(sem_col)
    sem_crs = gpd.GeoDataFrame(
        {"CODI_CART": ["1"], "DESC_LOGR": ["R"], "TIPO_IMOVE": ["PREDIAL"]}, geometry=[box(0, 0, 1, 1)]
    )
    with pytest.raises(ValueError, match="CRS"):
        normalizar(sem_crs)


def test_atribuir_bairro_pelo_ponto_interno():
    lotes = _lotes([("1", "PREDIAL", 0), ("2", "PREDIAL", 200)]).drop(columns="bairro")
    bairros = gpd.GeoDataFrame({"N_BAIRRO": ["TORRE"]}, geometry=[box(-5, -5, 100, 100)], crs=SRID)
    out = atribuir_bairro(lotes, bairros)
    assert out["bairro"].iloc[0] == "TORRE"
    assert out["bairro"].isna().iloc[1]  # fora de qualquer bairro


def test_diff_classifica_novo_removido_alterado_e_igual():
    atual = _lotes([("A", "TERRITORIAL", 0), ("B", "TERRITORIAL", 100), ("C", "PREDIAL", 200)])
    novo = _lotes([("A", "TERRITORIAL", 0), ("B", "PREDIAL", 100), ("D", "TERRITORIAL", 300)])
    d = calcular_diff(atual, novo)
    assert d.novos == ["D"]
    assert d.removidos == ["C"]
    assert d.alterados == ["B"]
    linha = d.detalhe.set_index("inscricao").loc["B"]
    assert (linha["tipo_antes"], linha["tipo_depois"], linha["mudou"]) == ("TERRITORIAL", "PREDIAL", "tipo")


def test_diff_ignora_ruido_de_geometria_mas_pega_mudanca_real():
    atual = _lotes([("A", "PREDIAL", 0), ("B", "PREDIAL", 100)])
    novo = atual.copy()
    novo.loc[0, "geometry"] = MultiPolygon([box(0.0001, 0, 20, 20)])       # 0,002 m² de diferença
    novo.loc[1, "geometry"] = MultiPolygon([box(100, 0, 125, 20)])          # +100 m² (desmembramento)
    d = calcular_diff(atual, novo)
    assert d.alterados == ["B"]
    assert d.detalhe.set_index("inscricao").loc["B", "mudou"] == "geom"


def test_diff_inscricao_duplicada_vai_para_apaga_e_reinsere():
    atual = _lotes([("A", "PREDIAL", 0), ("A", "PREDIAL", 100), ("B", "PREDIAL", 200)])
    novo = _lotes([("A", "PREDIAL", 0), ("B", "PREDIAL", 200), ("B", "PREDIAL", 300)])
    d = calcular_diff(atual, novo)
    assert d.duplicadas == ["A", "B"]
    assert d.novos == d.removidos == d.alterados == []
    assert set(d.apagar) == set(d.inserir) == {"A", "B"}


def test_diff_inscricao_duplicada_identica_nao_e_mexida():
    atual = _lotes([("A", "PREDIAL", 0), ("A", "PREDIAL", 100)])
    novo = atual.iloc[::-1].reset_index(drop=True)  # mesma coisa, outra ordem
    d = calcular_diff(atual, novo)
    assert d.duplicadas == d.apagar == d.inserir == []


def test_validar_passa_base_saudavel():
    atual = _lotes([(str(i), "TERRITORIAL" if i % 8 == 0 else "PREDIAL", i * 30) for i in range(100)])
    assert validar(len(atual), atual, calcular_diff(atual, atual)) == []


def test_validar_barra_base_que_encolhe_e_perde_lotes():
    """Cenário do WFS em 09/2026: recorte mais velho, ~5% menor que o cadastro atual."""
    atual = _lotes([(str(i), "TERRITORIAL" if i % 8 == 0 else "PREDIAL", i * 30) for i in range(100)])
    n_manter = int(100 * (1 - VARIACAO_TOTAL_MAX)) - 1
    novo = atual.iloc[:n_manter].copy()
    problemas = validar(len(atual), novo, calcular_diff(atual, novo))
    assert any("variou" in p for p in problemas)
    assert any("sairiam" in p for p in problemas)
    assert (100 - n_manter) / 100 > REMOVIDOS_MAX


def test_validar_barra_tipo_desconhecido_e_bairro_faltando():
    atual = _lotes([(str(i), "TERRITORIAL" if i % 8 == 0 else "PREDIAL", i * 30) for i in range(100)])
    novo = atual.copy()
    novo.loc[0, "tipo"] = "GLEBA"
    novo.loc[:9, "bairro"] = None
    problemas = validar(len(atual), novo, calcular_diff(atual, novo))
    assert any("GLEBA" in p for p in problemas)
    assert any("sem bairro" in p for p in problemas)


def test_validar_barra_fracao_de_vagos_implausivel():
    atual = _lotes([(str(i), "PREDIAL", i * 30) for i in range(100)])
    problemas = validar(len(atual), atual, calcular_diff(atual, atual))
    assert any("fração de vagos" in p for p in problemas)


def test_resumo_de_base_identica():
    atual = _lotes([("A", "TERRITORIAL", 0), ("B", "PREDIAL", 100)])
    texto = resumo(calcular_diff(atual, atual), atual, len(atual))
    assert "novos: 0 | removidos: 0 | alterados: 0" in texto
    assert "geometria mudou: 0" in texto


def test_normalizar_aceita_polygon_simples():
    bruto = gpd.GeoDataFrame(
        {"CODI_CART": ["1"], "DESC_LOGR": ["R"], "TIPO_IMOVE": ["PREDIAL"]},
        geometry=[Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])], crs=SRID,
    )
    assert normalizar(bruto).geom_type.tolist() == ["MultiPolygon"]
