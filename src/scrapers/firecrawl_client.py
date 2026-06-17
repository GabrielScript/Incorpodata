"""Cliente fino do Firecrawl (serviço gerenciado) para coleta respeitosa.

Sem burla de anti-bot: usa o proxy 'basic' do Firecrawl (renderização gerenciada),
NÃO os modos 'stealth'/'enhanced' de evasão. Chave via env (FIRECRAWL_API_KEY).
"""
from __future__ import annotations

import os

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

API_URL = "https://api.firecrawl.dev/v1/scrape"

# Schema/prompt de extração dos cards de listagem (terrenos à venda).
LISTING_SCHEMA = {
    "type": "object",
    "properties": {
        "blocked": {"type": "boolean"},
        "listings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "titulo": {"type": "string"},
                    "preco": {"type": "number"},
                    "area_m2": {"type": "number"},
                    "endereco": {"type": "string"},
                    "bairro": {"type": "string"},
                },
            },
        },
    },
}
PROMPT = (
    "Extraia TODOS os anúncios de terrenos/lotes à venda listados na página. Para cada um: "
    "url do anúncio (link completo), título, preço em reais (apenas número), área em m² "
    "(apenas número), endereço/rua e bairro. Se a página for um desafio/captcha/bloqueio, "
    "retorne blocked=true."
)


class FirecrawlError(RuntimeError):
    pass


def _key() -> str:
    k = os.getenv("FIRECRAWL_API_KEY")
    if not k:
        raise FirecrawlError(
            "FIRECRAWL_API_KEY ausente. Defina no .env (serviço gerenciado Firecrawl)."
        )
    return k


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def scrape_listings(url: str, *, wait_for: int = 5000, timeout: int = 120) -> list[dict]:
    """Raspa uma página de listagem e devolve os itens brutos (dicts) extraídos.

    Levanta FirecrawlError se a página vier bloqueada (anti-bot) — NÃO escalamos p/ evasão.
    """
    resp = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
        json={
            "url": url,
            "formats": ["json"],
            "onlyMainContent": True,
            "waitFor": wait_for,
            "proxy": "basic",  # gerenciado, sem evasão
            "jsonOptions": {"prompt": PROMPT, "schema": LISTING_SCHEMA},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    data = (payload.get("data") or {}).get("json") or {}
    if data.get("blocked"):
        raise FirecrawlError(f"página bloqueada por anti-bot: {url} (não escalamos p/ evasão)")
    return data.get("listings") or []
