"""Fontes de anúncios + parsing puro (testável, sem rede/DB).

Cada fonte expõe a(s) URL(s) de listagem de terrenos em João Pessoa e o id da origem
é extraído da URL do anúncio. As funções de limpeza toleram número (vindo do Firecrawl
em JSON) ou string ("R$ 210.000,00", "360 m²").
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# URLs de listagem de terrenos à venda em João Pessoa por fonte.
SOURCES: dict[str, list[str]] = {
    "chavesnamao": [
        "https://www.chavesnamao.com.br/terrenos-a-venda/pb-joao-pessoa/",
    ],
    "vivareal": [
        "https://www.vivareal.com.br/venda/paraiba/joao-pessoa/lote-terreno_residencial/",
    ],
}

_ID_RE = re.compile(r"id-(\d+)")


def fonte_id_from_url(url: str | None) -> str | None:
    """Extrai o id do anúncio na origem a partir da URL (chavesnamao e vivareal usam '…id-<n>…')."""
    if not url:
        return None
    m = _ID_RE.search(url)
    return m.group(1) if m else None


def clean_preco(v: object) -> float | None:
    """Preço -> float em reais. Aceita número ou string BR ('R$ 1.059.000,00')."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if v > 0 else None
    s = re.sub(r"[^\d.,]", "", str(v))
    if not s:
        return None
    # BR: '.' = milhar, ',' = decimal. Sem vírgula, todo '.' é milhar (preços são inteiros).
    s = s.replace(".", "").replace(",", ".") if "," in s else s.replace(".", "")
    try:
        n = float(s)
    except ValueError:
        return None
    return n if n > 0 else None


def clean_area(v: object) -> float | None:
    """Área -> float em m². Aceita número ou string ('360 m²', '2.304 m²')."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if v > 0 else None
    s = re.sub(r"[^\d.,]", "", str(v))
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".") if "," in s else s.replace(".", "")
    try:
        n = float(s)
    except ValueError:
        return None
    return n if n > 0 else None


def clean_bairro(v: object) -> str | None:
    """Normaliza o texto do bairro (trim + colapsa espaços). Não força caixa (match usa upper)."""
    if not v:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s or None


@dataclass(frozen=True)
class Anuncio:
    """Anúncio normalizado, pronto p/ upsert em market.anuncios."""
    fonte: str
    fonte_id: str
    url: str
    titulo: str | None
    preco: float | None
    area_anunc_m2: float | None
    bairro_texto: str | None


def normalize(fonte: str, raw: dict) -> Anuncio | None:
    """Converte um item bruto do Firecrawl em Anuncio. Descarta sem url/id ou sem preço E área."""
    url = (raw.get("url") or "").strip()
    fid = fonte_id_from_url(url)
    if not url or not fid:
        return None
    preco = clean_preco(raw.get("preco"))
    area = clean_area(raw.get("area_m2"))
    if preco is None and area is None:
        return None  # sem nada útil
    return Anuncio(
        fonte=fonte,
        fonte_id=fid,
        url=url,
        titulo=(raw.get("titulo") or None),
        preco=preco,
        area_anunc_m2=area,
        bairro_texto=clean_bairro(raw.get("bairro")),
    )
