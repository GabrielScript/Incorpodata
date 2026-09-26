"""Parsing puro do inventário do BestPlaces -> linhas de market.anuncios (camada "À venda").

O BestPlaces (app irmão, "Tinder de imóveis") raspa ZAP/VivaReal, OLX, Chaves na Mão e
Imovelweb da Grande JP e remove duplicados entre portais (`imoveis_seed_full.json` / `imoveis_jp.json`).
Daqui sai só o que interessa à originação de terreno:
  - terrenos/lotes (inclusive em condomínio) -> casam com lote VAGO;
  - casas (inclusive comerciais) -> terreno "disfarçado": demolir e incorporar.
Apartamento/flat/sala ficam fora (são comps, não oportunidade de terreno).

Sem rede/DB: testável. LGPD: anunciante = nome + CRECI; telefone NUNCA sai daqui.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from src.scrapers.sources import clean_area, clean_bairro, clean_preco

# Faixas do selo de oportunidade — as mesmas do card do BestPlaces (bestplaces-web/src/lib/deal.ts).
CONF_MIN = 0.25          # abaixo disso a dispersão domina: não crava "oportunidade"
TIER_RARA = 0.45
TIER_BOA = 0.20
TIER_MERCADO = -0.10


def _ascii(s: object) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or ""))
                   if not unicodedata.combining(c)).lower().strip()


def categoria(tipo: str | None) -> str | None:
    """'terreno' | 'casa' | None (fora da camada À venda)."""
    t = _ascii(tipo)
    if not t:
        return None
    if "terreno" in t or "lote" in t:
        return "terreno"
    if "condominio" in t:          # casa em condomínio fechado: o lote é do condomínio
        return None
    if t.startswith("casa") or "sobrado" in t:
        return "casa"
    return None


# "terreno de 360 m²", "terreno com 450,5m2", "lote medindo 12x30", "área do terreno: 300 m²"
_NUM = r"(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d{2,6}(?:[.,]\d{1,2})?)"   # "1.200" | "450,5" | "360"
_TERRENO_M2 = re.compile(r"(?:terreno|lote)[^\d]{0,25}?" + _NUM + r"\s*(?:m2|m²|metros)", re.I)
_DIMENSOES = re.compile(
    r"(?:terreno|lote)[^\d]{0,25}?(\d{1,3}(?:[.,]\d{1,2})?)\s*[xX×]\s*(\d{1,3}(?:[.,]\d{1,2})?)", re.I)
_MILHAR = re.compile(r"\d{1,3}(?:\.\d{3})+")


def _f(s: str) -> float:
    """Número em formato BR: '1.200' (milhar), '450,5' (decimal), '12.5' (decimal)."""
    if "," in s:
        return float(s.replace(".", "").replace(",", "."))
    if _MILHAR.fullmatch(s):
        return float(s.replace(".", ""))
    return float(s)


def area_terreno_texto(texto: str | None) -> float | None:
    """Área do TERRENO de uma casa lida da descrição (o anúncio de casa traz área construída)."""
    if not texto:
        return None
    m = _TERRENO_M2.search(texto)
    if m:
        v = _f(m.group(1))
        if 40 <= v <= 100_000:
            return v
    m = _DIMENSOES.search(texto)
    if m:
        v = _f(m.group(1)) * _f(m.group(2))
        if 40 <= v <= 100_000:
            return v
    return None


def oportunidade_tier(desconto: float | None, confiabilidade: float | None,
                      suspeito: bool | None) -> str | None:
    """Selo do anúncio. desconto = (esperado − pedido)/esperado (>0 = abaixo do mercado)."""
    if desconto is None:
        return None
    if suspeito:
        return "suspeito"
    conf = (confiabilidade or 0.0) >= CONF_MIN
    if desconto > TIER_RARA and conf:
        return "rara"
    if desconto > TIER_BOA:
        return "boa" if conf else "incerta"
    if desconto >= TIER_MERCADO:
        return "mercado"
    return "acima"


@dataclass(frozen=True)
class AnuncioBP:
    fonte: str
    fonte_id: str
    url: str
    titulo: str | None
    tipo: str
    categoria: str                   # terreno | casa
    preco: float
    area_anunc_m2: float | None      # terreno: área do lote; casa: área construída
    area_terreno_m2: float | None    # terreno: = área; casa: lida do texto (ou None)
    bairro: str | None
    logradouro: str | None           # rua anunciada: confere o pino no casamento com o lote
    quartos: int | None
    banheiros: int | None
    suites: int | None
    vagas: int | None
    iptu: float | None
    condominio: float | None
    anunciante_nome: str | None
    anunciante_creci: str | None
    lat: float | None
    lon: float | None
    loc_aproximada: bool
    imagem_url: str | None
    scraped_at: str | None
    fontes: tuple[str, ...] = field(default_factory=tuple)


def _i(v: object) -> int | None:
    try:
        return int(v) if v not in (None, "") else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def comodo(v: object) -> int | None:
    """Quartos/banheiros/suítes: os portais gravam 0 quando o campo não foi informado."""
    n = _i(v)
    return n if n else None


def _fl(v: object) -> float | None:
    try:
        n = float(v) if v not in (None, "") else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return n if n and n > 0 else None


def _coord(v: object) -> float | None:
    try:
        n = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return n if n != 0 else None


def from_record(raw: dict) -> AnuncioBP | None:
    """Registro do seed do BestPlaces -> AnuncioBP. None se não é terreno/casa de venda válido."""
    cat = categoria(raw.get("type"))
    if cat is None or (raw.get("business") or "SALE") != "SALE":
        return None
    fonte_id = raw.get("id")
    url = raw.get("url")
    preco = clean_preco(raw.get("price"))
    if not fonte_id or not url or preco is None:
        return None
    area = clean_area(raw.get("area_max")) or clean_area(raw.get("area_min"))
    if cat == "terreno":
        area_terreno = clean_area(raw.get("area_total")) or area
    else:
        area_terreno = area_terreno_texto(raw.get("description")) or area_terreno_texto(raw.get("title"))
    adv = raw.get("advertiser") or {}
    imgs = raw.get("images") or []
    lat, lon = _coord(raw.get("lat")), _coord(raw.get("lng"))
    return AnuncioBP(
        fonte=str(raw.get("source") or "bestplaces"),
        fonte_id=str(fonte_id),
        url=str(url),
        titulo=raw.get("title"),
        tipo=str(raw.get("type")),
        categoria=cat,
        preco=preco,
        area_anunc_m2=area,
        area_terreno_m2=area_terreno,
        bairro=clean_bairro(raw.get("neighborhood")),
        logradouro=clean_bairro(raw.get("street")),
        # terreno não tem cômodos: o que vier do portal é o default do formulário
        quartos=comodo(raw.get("bedrooms")) if cat == "casa" else None,
        banheiros=comodo(raw.get("bathrooms")) if cat == "casa" else None,
        suites=comodo(raw.get("suites")) if cat == "casa" else None,
        vagas=_i(raw.get("parking")) if cat == "casa" else None,
        iptu=_fl(raw.get("iptu")),
        condominio=_fl(raw.get("condo_fee")),
        anunciante_nome=adv.get("name") or None,
        anunciante_creci=(str(adv["creci"]) if adv.get("creci") else None),
        lat=lat if lon is not None else None,
        lon=lon if lat is not None else None,
        loc_aproximada=bool(raw.get("approx_location")),
        imagem_url=imgs[0] if imgs else None,
        scraped_at=raw.get("scraped_at"),
        fontes=tuple(s for s in (raw.get("sources") or [raw.get("source")]) if s),
    )
