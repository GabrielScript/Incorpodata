"""Geocodificação de comps sem coordenada (Nominatim/OSM) — parte pura, sem rede/DB.

Só geocodificamos comp COM endereço de rua (street). Comp só com bairro fica sem geom
de propósito: jogar tudo no centroide do bairro empilharia pontos idênticos e distorceria
a mediana por raio do lote — e o caso "bairro" já é coberto pela view market.preco_m2_bairro.

Rede + DB (throttle 1 req/s, cache em market.geocode_cache, UPDATE em market.comps)
ficam em src.scrapers.geocode_comps; aqui é testável offline.
"""
from __future__ import annotations

import re
import unicodedata

CITY_SUFFIX = "João Pessoa, Paraíba, Brasil"

# Envelope generoso de João Pessoa (graus, EPSG:4326). Resultado fora disso = Nominatim
# casou rua homônima de outra cidade → descartar em vez de plotar comp em Recife.
JP_LAT = (-7.35, -7.00)
JP_LON = (-35.02, -34.77)

# viewbox do Nominatim: lon1,lat1,lon2,lat2. Com bounded=1 a busca nem sai do envelope.
_VIEWBOX = f"{JP_LON[0]},{JP_LAT[0]},{JP_LON[1]},{JP_LAT[1]}"


def _clean(s: str | None) -> str | None:
    """Trim + colapsa espaços. None/vazio -> None."""
    if not s:
        return None
    out = re.sub(r"\s+", " ", str(s)).strip()
    return out or None


def build_query(endereco: str | None, bairro: str | None) -> str | None:
    """Consulta freeform p/ o Nominatim: 'rua, bairro, João Pessoa, Paraíba, Brasil'.

    None sem endereço de rua — bairro sozinho não é geocodificável (ver docstring do módulo).
    O bairro entra na consulta p/ desambiguar rua repetida entre bairros.
    """
    end = _clean(endereco)
    if end is None:
        return None
    parts = [end]
    b = _clean(bairro)
    if b is not None:
        parts.append(b)
    parts.append(CITY_SUFFIX)
    return ", ".join(parts)


def _norm_key_part(s: str | None) -> str:
    """Mesma normalização de normalize_bairro_key: NFKD sem acento, caixa alta, só A-Z0-9."""
    if not s:
        return ""
    ascii_str = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]", "", ascii_str.upper())


def cache_key(endereco: str | None, bairro: str | None) -> str:
    """Chave estável de market.geocode_cache: 'ENDERECO|BAIRRO' normalizados.

    Insensível a caixa/acento/pontuação — 'Av. Epitácio' e 'av epitacio' são a mesma
    consulta e não podem gastar duas requisições no Nominatim (1 req/s).
    """
    return f"{_norm_key_part(endereco)}|{_norm_key_part(bairro)}"


def nominatim_params(query: str) -> dict[str, str]:
    """Parâmetros da busca no Nominatim, restrita ao envelope de João Pessoa."""
    return {
        "q": query,
        "format": "jsonv2",
        "limit": "1",
        "viewbox": _VIEWBOX,
        "bounded": "1",
    }


def parse_nominatim(payload: object) -> tuple[float, float] | None:
    """Resposta do Nominatim (lista) -> (lat, lon) validado no envelope de JP. None se inútil."""
    if not payload or not isinstance(payload, list):
        return None
    first = payload[0]
    if not isinstance(first, dict):
        return None
    try:
        lat = float(first["lat"])
        lon = float(first["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (JP_LAT[0] <= lat <= JP_LAT[1] and JP_LON[0] <= lon <= JP_LON[1]):
        return None
    return (lat, lon)
