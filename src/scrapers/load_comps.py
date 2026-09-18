"""Ingere comps de venda (imoveis_jp.json) em market.comps → base do R$/m² por bairro.

Uso:
    python -m src.scrapers.load_comps                       # usa ./imoveis_jp.json
    python -m src.scrapers.load_comps --file dados.json
    python -m src.scrapers.load_comps --dry-run             # parseia + mostra R$/m² por bairro (sem DB)
    python -m src.scrapers.load_comps --dry-run --tipo Casa

Idempotente: ON CONFLICT (source, source_id) atualiza preço/área. O --dry-run roda 100%
offline (sem Postgres) e replica o filtro da view (R$/m² 800–30000) — serve de verificação.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import text

from src.scrapers.comps import (
    Comp,
    comp_from_record,
    filter_to_official,
    normalize_bairro_key,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILE = ROOT / "imoveis_jp.json"

# Mesmo saneamento da view market.preco_m2_bairro (mantém dry-run ≡ banco).
PRECO_M2_MIN, PRECO_M2_MAX = 800.0, 30000.0

# Precedência de coordenada no reload (EXCLUDED = linha nova):
#   - reload SEM coordenada nunca apaga geom existente (inclusive a geocodificada);
#   - o portal manda na própria coordenada ('fonte'/'fonte_aprox' — reload corrige o rótulo);
#   - só 'nominatim' (nível de rua, do backfill) resiste a pino aproximado do portal.
# IS NOT DISTINCT FROM: geo_fonte NULL (linha pré-migração) não pode anular o predicado —
# `NULL = 'nominatim'` é NULL, NULL AND true é NULL, e o CASE cairia no ELSE sem rotular.
_TAKE = (
    "(EXCLUDED.geom IS NOT NULL AND NOT "
    "(market.comps.geo_fonte IS NOT DISTINCT FROM 'nominatim' AND EXCLUDED.geo_fonte = 'fonte_aprox'))"
)

_UPSERT = text(
    f"""
    INSERT INTO market.comps
      (source, source_id, tipo, business, preco, area_m2, quartos, vagas, bairro, endereco,
       lat, lon, geom, geo_fonte)
    VALUES
      (:source, :source_id, :tipo, :business, :preco, :area_m2, :quartos, :vagas, :bairro, :endereco,
       :lat, :lon,
       CASE WHEN :lat IS NOT NULL AND :lon IS NOT NULL
            THEN ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 31985) END,
       CASE WHEN :lat IS NOT NULL AND :lon IS NOT NULL
            THEN CASE WHEN :loc_aproximada THEN 'fonte_aprox' ELSE 'fonte' END END)
    ON CONFLICT (source, source_id) DO UPDATE SET
      tipo = EXCLUDED.tipo, business = EXCLUDED.business, preco = EXCLUDED.preco,
      area_m2 = EXCLUDED.area_m2, quartos = EXCLUDED.quartos, vagas = EXCLUDED.vagas,
      bairro = EXCLUDED.bairro,
      endereco = COALESCE(EXCLUDED.endereco, market.comps.endereco),
      lat       = CASE WHEN {_TAKE} THEN EXCLUDED.lat       ELSE market.comps.lat       END,
      lon       = CASE WHEN {_TAKE} THEN EXCLUDED.lon       ELSE market.comps.lon       END,
      geom      = CASE WHEN {_TAKE} THEN EXCLUDED.geom      ELSE market.comps.geom      END,
      geo_fonte = CASE WHEN {_TAKE} THEN EXCLUDED.geo_fonte ELSE market.comps.geo_fonte END,
      carregado_em = now()
    """
)


def load_records(path: Path) -> list[Comp]:
    """Lê o JSON (lista de imóveis) e normaliza; descarta o que não tem preço/área/bairro/id."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return [c for c in (comp_from_record(r) for r in data) if c]


def dedup(comps: list[Comp]) -> list[Comp]:
    """Remove duplicatas por (source, source_id), mantendo a primeira ocorrência."""
    seen: dict[tuple[str, str], Comp] = {}
    for c in comps:
        seen.setdefault((c.source, c.source_id), c)
    return list(seen.values())


def fetch_bairros_canon() -> dict[str, str]:
    """Whitelist autoritativa: {chave normalizada -> grafia oficial} dos bairros de geo.lotes."""
    from src.db.database import get_engine

    with get_engine().connect() as conn:
        rows = conn.execute(
            text("SELECT DISTINCT bairro FROM geo.lotes WHERE bairro IS NOT NULL")
        ).all()
    return {normalize_bairro_key(b): b for (b,) in rows}


def preco_m2_por_bairro(comps: list[Comp], tipo: str, min_n: int = 15) -> list[tuple]:
    """Mediana/Q1/Q3/N de R$/m² por bairro p/ um tipo (offline, espelha a view)."""
    by: dict[str, list[float]] = defaultdict(list)
    for c in comps:
        if c.tipo != tipo:
            continue
        ppm = c.preco / c.area_m2
        if PRECO_M2_MIN <= ppm <= PRECO_M2_MAX:
            by[c.bairro].append(ppm)
    rows = []
    for bairro, vals in by.items():
        if len(vals) < min_n:
            continue
        q = st.quantiles(vals, n=4) if len(vals) >= 4 else [min(vals), st.median(vals), max(vals)]
        rows.append((bairro, len(vals), st.median(vals), q[0], q[2]))
    return sorted(rows, key=lambda r: -r[2])


def upsert(comps: list[Comp], chunk: int = 1000) -> int:
    """Grava em market.comps em lotes (executemany). Geom derivada de lat/lon quando houver."""
    from src.db.database import get_engine

    eng = get_engine()
    rows = [
        {
            "source": c.source, "source_id": c.source_id, "tipo": c.tipo, "business": c.business,
            "preco": c.preco, "area_m2": c.area_m2, "quartos": c.quartos, "vagas": c.vagas,
            "bairro": c.bairro, "endereco": c.endereco, "lat": c.lat, "lon": c.lon,
            "loc_aproximada": c.loc_aproximada,
        }
        for c in comps
    ]
    with eng.begin() as conn:
        for i in range(0, len(rows), chunk):
            conn.execute(_UPSERT, rows[i : i + chunk])
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Carrega comps de venda -> market.comps")
    ap.add_argument("--file", type=str, default=str(DEFAULT_FILE), help="JSON de imóveis (lista)")
    ap.add_argument("--dry-run", action="store_true", help="não grava; mostra R$/m² por bairro (offline)")
    ap.add_argument("--tipo", default="Apartamento", help="tipo p/ o resumo do --dry-run")
    args = ap.parse_args(argv)

    path = Path(args.file)
    if not path.exists():
        print(f"[erro] arquivo não encontrado: {path}")
        return 2

    comps = dedup(load_records(path))
    print(f"comps válidos (com id+preço+área+bairro): {len(comps)}")

    # Filtro de bairro oficial (geo.lotes): descarta neighborhood que é rua/avenida/fora de JP
    # e canoniza a grafia (casa com o bairro do lote no join do VGV).
    try:
        canon = fetch_bairros_canon()
        comps, rejeitados = filter_to_official(comps, canon)
        print(
            f"filtro de bairro: {len(canon)} bairros oficiais; "
            f"mantidos {len(comps)}, descartados {rejeitados} (bairro não-oficial)"
        )
    except Exception as exc:  # DB indisponível (ex.: --dry-run offline) → segue sem filtro
        print(f"[aviso] sem whitelist (DB indisponível: {exc.__class__.__name__}); ingestão SEM filtro")

    if args.dry_run:
        rows = preco_m2_por_bairro(comps, args.tipo)
        print(f"\nR$/m2 - {args.tipo} (bairros com >=15 comps, outliers saneados):")
        print(f"{'BAIRRO':<28}{'N':>5}{'MEDIANA':>12}{'Q1':>10}{'Q3':>10}")
        for bairro, n, med, q1, q3 in rows[:30]:
            print(f"{bairro[:27]:<28}{n:>5}{med:>12,.0f}{q1:>10,.0f}{q3:>10,.0f}")
        return 0

    n = upsert(comps)
    from src.db.database import get_engine

    with get_engine().connect() as conn:
        top = conn.execute(
            text(
                """
                SELECT bairro, n, round(preco_m2_mediana) AS mediana
                FROM market.preco_m2_bairro
                WHERE tipo = 'Apartamento' AND n >= 15
                ORDER BY preco_m2_mediana DESC LIMIT 8
                """
            )
        ).all()
    print(f"upsert de {n} comps em market.comps.")
    print("top bairros (apto, R$/m² mediana):")
    for bairro, nn, mediana in top:
        print(f"  {bairro:<26} n={nn:<5} R$ {mediana:,.0f}/m²")
    return 0


if __name__ == "__main__":
    sys.exit(main())
