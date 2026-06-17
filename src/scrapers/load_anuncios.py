"""Coleta anúncios de terrenos de JP e faz upsert em market.anuncios.

Uso:
    python -m src.scrapers.load_anuncios                 # ao vivo (precisa FIRECRAWL_API_KEY)
    python -m src.scrapers.load_anuncios --from-file data/raw/anuncios_jp_sample.json
    python -m src.scrapers.load_anuncios --dry-run       # não grava, só conta

Idempotente: ON CONFLICT (fonte, fonte_id) atualiza preço/área e ultimo_visto.
LGPD: grava url+preço+área+bairro; NUNCA telefone. Casar anúncio→lote (geocoding) é o
próximo passo (market.anuncio_lote) — ainda não feito aqui.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from sqlalchemy import text

from src.db.database import get_engine
from src.scrapers.sources import SOURCES, Anuncio, normalize

ROOT = Path(__file__).resolve().parents[2]

_UPSERT = text(
    """
    INSERT INTO market.anuncios
      (fonte, fonte_id, url, titulo, preco, area_anunc_m2, bairro_texto, ativo, ultimo_visto)
    VALUES (:fonte, :fonte_id, :url, :titulo, :preco, :area, :bairro, true, now())
    ON CONFLICT (fonte, fonte_id) DO UPDATE SET
      url = EXCLUDED.url, titulo = EXCLUDED.titulo, preco = EXCLUDED.preco,
      area_anunc_m2 = EXCLUDED.area_anunc_m2, bairro_texto = EXCLUDED.bairro_texto,
      ativo = true, ultimo_visto = now()
    """
)


def collect_live(delay_s: float = 2.0) -> list[Anuncio]:
    """Raspa todas as fontes ao vivo (Firecrawl). Rate-limit entre páginas; fonte que falha não aborta."""
    from src.scrapers.firecrawl_client import FirecrawlError, scrape_listings

    out: list[Anuncio] = []
    for fonte, urls in SOURCES.items():
        for url in urls:
            try:
                raw = scrape_listings(url)
                print(f"[ok]   {fonte}: {len(raw)} itens brutos de {url}")
            except FirecrawlError as exc:
                print(f"[FALHA] {fonte}: {exc}")
                continue
            out.extend(a for a in (normalize(fonte, r) for r in raw) if a)
            time.sleep(delay_s)
    return out


def collect_from_file(path: Path) -> list[Anuncio]:
    """Lê itens brutos de um JSON {fonte: [ {url,preco,area_m2,bairro,...}, ... ]}."""
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[Anuncio] = []
    for fonte, items in data.items():
        out.extend(a for a in (normalize(fonte, r) for r in items) if a)
    return out


def dedup(anuncios: list[Anuncio]) -> list[Anuncio]:
    """Remove duplicatas por (fonte, fonte_id), mantendo a primeira ocorrência."""
    seen: dict[tuple[str, str], Anuncio] = {}
    for a in anuncios:
        seen.setdefault((a.fonte, a.fonte_id), a)
    return list(seen.values())


def upsert(anuncios: list[Anuncio]) -> int:
    eng = get_engine()
    with eng.begin() as conn:
        for a in anuncios:
            conn.execute(
                _UPSERT,
                {
                    "fonte": a.fonte, "fonte_id": a.fonte_id, "url": a.url, "titulo": a.titulo,
                    "preco": a.preco, "area": a.area_anunc_m2, "bairro": a.bairro_texto,
                },
            )
    return len(anuncios)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Coleta anúncios de terrenos -> market.anuncios")
    ap.add_argument("--from-file", type=str, help="JSON {fonte:[itens]} em vez de coleta ao vivo")
    ap.add_argument("--dry-run", action="store_true", help="não grava; só mostra o que coletou")
    args = ap.parse_args(argv)

    if args.from_file:
        anuncios = collect_from_file(Path(args.from_file))
    else:
        anuncios = collect_live()
    anuncios = dedup(anuncios)

    com_preco = sum(1 for a in anuncios if a.preco is not None)
    print(f"coletados {len(anuncios)} anúncios únicos ({com_preco} com preço)")
    if args.dry_run:
        for a in anuncios[:10]:
            print(f"  {a.fonte} {a.fonte_id} | R$ {a.preco} | {a.area_anunc_m2} m² | {a.bairro_texto}")
        return 0

    n = upsert(anuncios)
    with get_engine().connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM market.anuncios WHERE ativo")).scalar()
    print(f"upsert de {n}; total ativo em market.anuncios = {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
