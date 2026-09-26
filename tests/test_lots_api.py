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
        "anuncio_tipo": None,
        "oportunidade_tier": None,
        "desconto_pct": None,
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


def test_lote_a_venda_traz_categoria_e_selo(api, monkeypatch):
    import src.api.lots as lots

    monkeypatch.setattr(lots, "ANUNCIOS_ATIVOS", True)
    client, conn = api(1)
    orig = conn.execute

    def com_anuncio(sql, params):
        res = orig(sql, params)
        res._rows[0] |= {"a_venda": True, "preco": 900000.0, "preco_m2": 2000.0,
                         "anuncio_tipo": "Terreno / Lote", "oportunidade_tier": "incerta",
                         "desconto_pct": 0.31}
        return res

    conn.execute = com_anuncio
    p = client.get("/api/lots", params={"a_venda": "true"}).json()["features"][0]["properties"]
    assert p["a_venda"] is True and p["anuncio_categoria"] == "terreno"
    assert p["oportunidade_tier"] == "incerta" and p["desconto_pct"] == 0.31
    # o SQL recebe os limites de frescor/score e o liga-desliga da camada
    assert conn.params["anuncios_ativos"] is True
    assert conn.params["max_dias"] == lots.ANUNCIO_MAX_DIAS
    assert conn.params["a_venda"] is True


def test_resposta_grande_sai_comprimida(api):
    # ~13 MB crus p/ a cidade inteira; o Cloud Run não comprime sozinho
    client, _ = api(2_000)
    r = client.get("/api/lots", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"
    # httpx já descomprime r.content; o header é que prova que saiu comprimido
    assert json.loads(r.content)["type"] == "FeatureCollection"
