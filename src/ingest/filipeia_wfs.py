"""Download de camadas do GeoServer público do Filipeia (WFS 2.0, GeoJSON).

O servidor está com disco cheio (09/2026): paginação (STARTINDEX) e filtro por BBOX dão 400
("Não há espaço disponível no dispositivo", ao ordenar/indexar). O GetFeature inteiro, sem
filtro, funciona — Lotes (~178 mil) = ~80 MB em ~30 s; EDIFICACOES (~290 mil) só com a
geometria = ~130 MB em ~30 s. Camadas quebradas do lado deles (shapefile inexistente no
servidor): Area_de_Preservacao_Permanente, LotesNaoCadastrados.
"""
from __future__ import annotations

import io
import re
import time

import geopandas as gpd
import requests

from src.db.database import INTERNAL_SRID

WFS_URL = "https://filipeia.joaopessoa.pb.gov.br/geoserver/wfs"
WFS_MAX_FEATURES = 400_000
TENTATIVAS = 3  # o servidor corta conexão no meio de downloads grandes (IncompleteRead)
_UA = {"User-Agent": "IncorpoData/1.0 (carga do cadastro)"}


def _get(url: str, params: dict[str, str | int], timeout: int) -> requests.Response:
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resp = requests.get(url, params=params, headers=_UA, timeout=timeout)
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as exc:
            if tentativa == TENTATIVAS:
                raise
            espera = 15 * tentativa
            print(f"  WFS: {type(exc).__name__}; nova tentativa em {espera}s ({tentativa}/{TENTATIVAS - 1})")
            time.sleep(espera)
    raise AssertionError("inalcançável")


def baixar_camada(
    typename: str, propriedades: list[str] | None = None, url: str = WFS_URL, timeout: int = 900
) -> gpd.GeoDataFrame:
    """Camada inteira em EPSG:INTERNAL_SRID. `typename` sem prefixo (ex.: 'Lotes').

    `propriedades` limita os atributos (a geometria `the_geom` sempre vem). Falha alto se o
    GeoServer devolver ExceptionReport ou menos feições do que anunciou (download pela metade).
    """
    params: dict[str, str | int] = {
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
        "TYPENAMES": f"digeoc:{typename}", "OUTPUTFORMAT": "application/json",
        "SRSNAME": f"EPSG:{INTERNAL_SRID}", "COUNT": WFS_MAX_FEATURES,
    }
    if propriedades:
        params["PROPERTYNAME"] = ",".join(["the_geom", *propriedades])
    resp = _get(url, params, timeout)
    if resp.content.lstrip().startswith(b"<"):  # ExceptionReport do GeoServer vem em XML
        raise RuntimeError(f"WFS {typename} devolveu erro: {resp.text[:400]}")
    gdf = gpd.read_file(io.BytesIO(resp.content))
    # numberMatched vem no fim do GeoJSON do GeoServer; evita parsear os MB de novo.
    achou = re.search(rb'"numberMatched":\s*(\d+)', resp.content[-2000:])
    if achou and int(achou.group(1)) != len(gdf):
        raise RuntimeError(f"WFS {typename} incompleto: {len(gdf)} de {int(achou.group(1))} feições")
    return gdf.set_crs(epsg=INTERNAL_SRID, allow_override=True)
