"""/api/lots no modo "Todos os bairros": o mapa tem que cobrir a cidade inteira.

Regressão: o teto padrão era 2000 lotes por id → "Todos os bairros" mostrava só 8 dos 64
bairros de JP (23.682 lotes vagos em 09/2026). Conexão falsa via dependency_overrides,
honrando o LIMIT como o Postgres faria — sem banco.
"""
import json

import pytest
from fastapi.testclient import TestClient

from src.api.db import get_conn
from src.api.lots import LIMITE_LOTES_MAPA
from src.api.main import app

VAGOS_JP = 23_682  # lotes TERRITORIAL no Neon em 09/2026
BAIRROS_JP = 64


def _lote(i: int, n: int) -> dict:
    # ids agrupados por bairro, como no cadastro (ORDER BY id percorre bairro a bairro)
    return {
        "id": 186_750 + i,
        "logradouro": f"RUA {i}",
        "bairro": f"BAIRRO {i * BAIRROS_JP // n:02d}",
        "tipo": "TERRITORIAL",
        "area_geom_m2": 360.0,
        "sigla": "ZR1",
        "area_projecao_max_m2": 180.0,
        "a_venda": False,
        "preco": None,
        "preco_m2": None,
        "alerta": i % 10 == 0,
        "geojson": '{"type":"Polygon","coordinates":[[[-34.8,-7.1],[-34.8,-7.2],[-34.9,-7.2],[-34.8,-7.1]]]}',
    }


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeConn:
    def __init__(self, n: int):
        self.n = n
        self.params: dict = {}

    def execute(self, _sql, params):
        self.params = params
        return _FakeResult([_lote(i, self.n) for i in range(min(self.n, params["limit"]))])


@pytest.fixture
def api():
    def usar(n: int) -> tuple[TestClient, _FakeConn]:
        conn = _FakeConn(n)
        app.dependency_overrides[get_conn] = lambda: conn
        return TestClient(app), conn

    yield usar
    app.dependency_overrides.pop(get_conn, None)


def test_todos_os_bairros_traz_a_cidade_inteira(api):
    client, _ = api(VAGOS_JP)
    fc = client.get("/api/lots", params={"bairro": "", "only_vacant": "true"}).json()
    assert len(fc["features"]) == VAGOS_JP
    assert len({f["properties"]["bairro"] for f in fc["features"]}) == BAIRROS_JP
    assert fc["truncado"] is False


def test_passou_do_teto_avisa_truncado(api):
    # "Todos" + construídos (186 mil) não cabe: corta no teto e diz que cortou
    client, conn = api(LIMITE_LOTES_MAPA + 10)
    fc = client.get("/api/lots", params={"bairro": "", "only_vacant": "false"}).json()
    assert len(fc["features"]) == LIMITE_LOTES_MAPA
    assert fc["truncado"] is True
    assert conn.params["limit"] == LIMITE_LOTES_MAPA + 1  # 1 a mais = detecta corte sem COUNT


def test_feature_geojson_valida(api):
    client, _ = api(3)
    f = client.get("/api/lots").json()["features"][0]
    assert f["type"] == "Feature" and f["id"] == 186_750
    assert f["geometry"]["type"] == "Polygon"
    assert f["properties"]["bairro"] == "BAIRRO 00"
    assert f["properties"]["geometria_suspeita"] is False


def test_lista_marca_lote_com_alerta_com_os_limiares_da_viabilidade(api):
    from src.api.viability import ALERTA_AGUA_PCT, ALERTA_EDIFICADO_PCT

    client, conn = api(11)
    feats = client.get("/api/lots").json()["features"]
    assert [f["properties"]["alerta"] for f in feats] == [i % 10 == 0 for i in range(11)]
    assert conn.params["alerta_edif_pct"] == ALERTA_EDIFICADO_PCT
    assert conn.params["alerta_agua_pct"] == ALERTA_AGUA_PCT


def test_anuncios_desligados_por_padrao(api):
    # só terreno do cadastro: o SQL nem casa anúncio (LATERAL ... ON false)
    client, conn = api(1)
    p = client.get("/api/lots").json()["features"][0]["properties"]
    assert conn.params["anuncios_ativos"] is False
    assert p["a_venda"] is False and p["preco"] is None


class _FakeTileConn:
    """Guarda SQL e parâmetros; devolve bytes no lugar do ST_AsMVT."""

    def __init__(self, mvt: bytes | None):
        self.mvt = mvt
        self.sql = ""
        self.params: dict = {}

    def execute(self, sql, params):
        self.sql, self.params = str(sql), params
        return self

    def scalar(self):
        return self.mvt


@pytest.fixture
def tiles():
    def usar(mvt: bytes | None = b"\x1a\x05lotes") -> tuple[TestClient, _FakeTileConn]:
        conn = _FakeTileConn(mvt)
        app.dependency_overrides[get_conn] = lambda: conn
        return TestClient(app), conn

    yield usar
    app.dependency_overrides.pop(get_conn, None)


def test_tile_mvt_com_os_mesmos_filtros_da_lista(tiles):
    import src.api.lots as lots

    client, conn = tiles()
    r = client.get("/api/tiles/lotes/14/6605/8517.pbf",
                   params={"bairro": "BESSA", "only_vacant": "false", "a_venda": "true", "area_min": 300})
    assert r.status_code == 200 and r.content == b"\x1a\x05lotes"
    assert r.headers["content-type"] == "application/vnd.mapbox-vector-tile"
    assert "max-age" in r.headers["cache-control"]
    assert {"z": 14, "x": 6605, "y": 8517}.items() <= conn.params.items()
    assert conn.params["bairro"] == "BESSA" and conn.params["only_vacant"] is False
    assert conn.params["a_venda"] is True and conn.params["area_min"] == 300
    assert "limit" not in conn.params  # tile não tem teto: a cidade inteira aparece
    assert lots._LOTES_FILTRADOS in conn.sql  # mesmo recorte da lista, por construção
    assert lots._ALERTA_SQL in conn.sql  # mapa pinta o alerta com a mesma regra da lista


def test_ranking_exclui_lote_com_alerta_pela_mesma_regra():
    """O topo das Oportunidades é o que o corretor abre primeiro: sem casa nem lagoa ali."""
    import inspect

    import src.api.lots as lots

    fonte = inspect.getsource(lots.list_oportunidades)
    assert "NOT {_ALERTA_SQL}" in fonte and "**_ALERTA_PARAMS" in fonte


def test_tile_vazio_e_fora_da_faixa(tiles):
    client, _ = tiles(None)
    assert client.get("/api/tiles/lotes/16/26421/34068.pbf").content == b""
    assert client.get("/api/tiles/lotes/12/1651/2129.pbf").status_code == 422  # z12 ≈ a cidade: GeoJSON
    assert client.get("/api/tiles/lotes/13/8192/0.pbf").status_code == 404  # fora da grade 2^13


def test_resposta_grande_sai_comprimida(api):
    # ~13 MB crus p/ a cidade inteira; o Cloud Run não comprime sozinho
    client, _ = api(2_000)
    r = client.get("/api/lots", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"
    # httpx já descomprime r.content; o header é que prova que saiu comprimido
    assert json.loads(r.content)["type"] == "FeatureCollection"
