"""Download do WFS do Filipeia: retentativa e detecção de resposta pela metade (sem rede)."""
import pytest
import requests

import src.ingest.filipeia_wfs as wfs

_GEOJSON = (
    b'{"type":"FeatureCollection","features":[{"type":"Feature","id":"Lotes.1","geometry":'
    b'{"type":"Polygon","coordinates":[[[0,0],[10,0],[10,10],[0,0]]]},"properties":{"CODI_CART":"1"}}],'
    b'"totalFeatures":1,"numberMatched":%d,"numberReturned":1}'
)


class _Resp:
    def __init__(self, content: bytes):
        self.content = content
        self.text = content.decode()

    def raise_for_status(self):
        pass


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(wfs.time, "sleep", lambda _s: None)


def test_retenta_conexao_cortada_e_devolve_a_camada(monkeypatch):
    chamadas = []

    def get(*_a, **_k):
        chamadas.append(1)
        if len(chamadas) == 1:
            raise requests.exceptions.ChunkedEncodingError("IncompleteRead")
        return _Resp(_GEOJSON % 1)

    monkeypatch.setattr(wfs.requests, "get", get)
    gdf = wfs.baixar_camada("Lotes", ["CODI_CART"])
    assert len(chamadas) == 2 and len(gdf) == 1
    assert gdf.crs.to_epsg() == 31985


def test_desiste_depois_das_tentativas(monkeypatch):
    def get(*_a, **_k):
        raise requests.ConnectionError("servidor fora")

    monkeypatch.setattr(wfs.requests, "get", get)
    with pytest.raises(requests.ConnectionError):
        wfs.baixar_camada("Lotes")


def test_exception_report_do_geoserver_falha_alto(monkeypatch):
    xml = b'<?xml version="1.0"?><ows:ExceptionReport>Nao ha espaco disponivel no dispositivo</ows:ExceptionReport>'
    monkeypatch.setattr(wfs.requests, "get", lambda *_a, **_k: _Resp(xml))
    with pytest.raises(RuntimeError, match="espaco"):
        wfs.baixar_camada("Lotes")


def test_download_pela_metade_falha_alto(monkeypatch):
    monkeypatch.setattr(wfs.requests, "get", lambda *_a, **_k: _Resp(_GEOJSON % 5))
    with pytest.raises(RuntimeError, match="incompleto: 1 de 5"):
        wfs.baixar_camada("Lotes")
