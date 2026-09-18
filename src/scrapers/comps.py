"""Parsing puro de comps de venda (imoveis_jp.json) -> linha de market.comps.

Comps são a camada de REFERÊNCIA de preço (R$/m² por bairro), base do VGV — distinta
de market.anuncios (gatilho de demanda, terreno casado a lote). Aqui só normalizamos um
registro bruto do scraper; sem rede/DB, por isso testável. O saneamento de outliers de
R$/m² é feito na view market.preco_m2_bairro (mantém a tabela fiel ao que foi raspado).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace

from src.scrapers.sources import clean_area, clean_bairro, clean_preco


@dataclass(frozen=True)
class Comp:
    """Comp normalizado, pronto p/ upsert em market.comps."""
    source: str
    source_id: str
    tipo: str | None
    business: str
    preco: float
    area_m2: float
    quartos: int | None
    vagas: int | None
    bairro: str
    endereco: str | None
    lat: float | None
    lon: float | None
    loc_aproximada: bool = False  # pino aproximado do portal (approx_location) — não é o endereço exato


def _int_or_none(v: object) -> int | None:
    try:
        return int(v) if v is not None else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _float_or_none(v: object) -> float | None:
    try:
        return float(v) if v is not None else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def normalize_bairro_key(s: str) -> str:
    """Chave de match de bairro: translitera acentos (NFKD) + caixa alta + só A-Z0-9.

    Translitera (Á→A) para o comp raspado SEM acento casar com o bairro oficial acentuado
    de geo.lotes. Strings de rua/avenida ('Av. Epitácio, 123') geram chave que não bate em
    nenhum bairro → descartadas no filtro.
    """
    ascii_str = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]", "", ascii_str.upper())


def canonical_bairro(name: str | None, bairros_canon: dict[str, str]) -> str | None:
    """Mapeia um texto de bairro p/ a grafia oficial (geo.lotes). None se não for bairro conhecido."""
    if not name:
        return None
    return bairros_canon.get(normalize_bairro_key(name))


def filter_to_official(
    comps: list[Comp], bairros_canon: dict[str, str]
) -> tuple[list[Comp], int]:
    """Mantém só comps em bairro oficial, canonizando a grafia. Retorna (mantidos, nº descartados)."""
    kept: list[Comp] = []
    rejeitados = 0
    for c in comps:
        canon = canonical_bairro(c.bairro, bairros_canon)
        if canon is None:
            rejeitados += 1
            continue
        kept.append(c if canon == c.bairro else replace(c, bairro=canon))
    return kept, rejeitados


def comp_from_record(raw: dict, source_default: str = "vivareal") -> Comp | None:
    """Converte um item de imoveis_jp.json em Comp. Descarta sem id/preço/área/bairro."""
    source_id = raw.get("id")
    if source_id is None:
        return None
    preco = clean_preco(raw.get("price"))
    area = clean_area(raw.get("area_min")) or clean_area(raw.get("area_max"))
    bairro = clean_bairro(raw.get("neighborhood"))
    if preco is None or area is None or bairro is None:
        return None
    return Comp(
        source=(raw.get("source") or source_default),
        source_id=str(source_id),
        tipo=(raw.get("type") or None),
        business=(raw.get("business") or "SALE"),
        preco=preco,
        area_m2=area,
        quartos=_int_or_none(raw.get("bedrooms")),
        vagas=_int_or_none(raw.get("parking")),
        bairro=bairro,
        # street alimenta o backfill de geocodificação (comp sem lat/lng — src.scrapers.geocode)
        endereco=clean_bairro(raw.get("street")),
        lat=_float_or_none(raw.get("lat")),
        lon=_float_or_none(raw.get("lng")),
        loc_aproximada=bool(raw.get("approx_location")),
    )
