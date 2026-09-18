"""Backfill de geom p/ comps sem coordenada, via Nominatim (OSM).

Uso:
    python -m src.scrapers.geocode_comps --dry-run       # mostra o que falta, sem rede/escrita
    python -m src.scrapers.geocode_comps --limit 300     # até 300 consultas novas (~5,5 min)

Regras do Nominatim: máx 1 req/s + User-Agent identificável — throttle embutido.
Cache em market.geocode_cache: consulta (mesmo a que falhou) nunca se repete; erro de
rede NÃO entra no cache (transitório — re-tenta na próxima rodada). Rodar offline/agendado
(pipeline), nunca no caminho de request da API.

Só entra geom de nível de RUA (comp com endereço). A parte pura (query, chave de cache,
parse, validação do envelope de JP) vive em src.scrapers.geocode — testada offline.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import requests
from sqlalchemy import text

from src.scrapers.geocode import build_query, cache_key, nominatim_params, parse_nominatim

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = os.getenv("NOMINATIM_UA", "IncorpoData/0.1 (analise urbanistica JP-PB; uso em lote 1req/s)")
THROTTLE_S = 1.1  # ToS do Nominatim: máx 1 req/s

# Sem geom OU com pino aproximado do portal: geocodificação por rua PROMOVE o comp
# ('fonte_aprox' → 'nominatim'), que volta a contar na mediana por raio.
_PENDENTES = text(
    """
    SELECT DISTINCT endereco, bairro
    FROM market.comps
    WHERE (geom IS NULL OR geo_fonte = 'fonte_aprox') AND endereco IS NOT NULL
    """
)

# Comps antigos (carregados antes da coluna geo_fonte) com coordenada da fonte.
_BACKFILL_GEO_FONTE = text(
    "UPDATE market.comps SET geo_fonte = 'fonte' WHERE geom IS NOT NULL AND geo_fonte IS NULL"
)

_CACHE_ALL = text("SELECT chave, lat, lon, ok FROM market.geocode_cache")

_CACHE_INSERT = text(
    """
    INSERT INTO market.geocode_cache (chave, consulta, lat, lon, ok)
    VALUES (:chave, :consulta, :lat, :lon, :ok)
    ON CONFLICT (chave) DO NOTHING
    """
)

# bairro IS NOT DISTINCT FROM: casa também o par com bairro NULL.
_APPLY = text(
    """
    UPDATE market.comps
    SET lat = :lat, lon = :lon,
        geom = ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 31985),
        geo_fonte = 'nominatim'
    WHERE (geom IS NULL OR geo_fonte = 'fonte_aprox')
      AND endereco = :endereco
      AND bairro IS NOT DISTINCT FROM :bairro
    """
)


def geocode_query(session: requests.Session, query: str) -> tuple[float, float] | None:
    """Uma consulta ao Nominatim. Levanta requests.RequestException em erro transitório."""
    resp = session.get(NOMINATIM_URL, params=nominatim_params(query), timeout=30)
    resp.raise_for_status()
    return parse_nominatim(resp.json())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Geocodifica comps sem coordenada (Nominatim)")
    ap.add_argument("--limit", type=int, default=300, help="teto de consultas NOVAS à rede")
    ap.add_argument("--dry-run", action="store_true", help="só relata pendências; sem rede/escrita")
    args = ap.parse_args(argv)

    from src.db.database import get_engine

    eng = get_engine()

    with eng.begin() as conn:
        n_legado = conn.execute(_BACKFILL_GEO_FONTE).rowcount
        pares = [(r[0], r[1]) for r in conn.execute(_PENDENTES).all()]
        cache = {r[0]: (r[1], r[2], r[3]) for r in conn.execute(_CACHE_ALL).all()}
    if n_legado:
        print(f"geo_fonte='fonte' marcado em {n_legado} comps legados (coordenada da fonte)")

    # Classifica os pares pendentes contra o cache.
    aplicaveis: list[tuple[str, str | None, float, float]] = []  # cache ok → só UPDATE
    ja_falhou = 0
    novos: list[tuple[str, str | None, str, str]] = []  # (endereco, bairro, chave, consulta)
    for endereco, bairro in pares:
        consulta = build_query(endereco, bairro)
        if consulta is None:
            continue
        chave = cache_key(endereco, bairro)
        hit = cache.get(chave)
        if hit is None:
            novos.append((endereco, bairro, chave, consulta))
        elif hit[2] and hit[0] is not None:
            aplicaveis.append((endereco, bairro, hit[0], hit[1]))
        else:
            ja_falhou += 1

    print(
        f"pendentes: {len(pares)} pares (endereço, bairro) sem geom | "
        f"cache ok p/ aplicar: {len(aplicaveis)} | cache falha (não re-tenta): {ja_falhou} | "
        f"novos p/ consultar: {len(novos)} (teto desta rodada: {args.limit})"
    )

    if args.dry_run:
        for endereco, bairro, _, consulta in novos[:10]:
            print(f"  consultaria: {consulta}")
        return 0

    atualizados = 0

    def flush(cache_rows: list[dict], pares_ok: list[tuple[str, str | None, float, float]]) -> int:
        """Commita um bloco (cache + UPDATEs). Incremental: queda no meio não perde o já feito."""
        n = 0
        with eng.begin() as conn:
            if cache_rows:
                conn.execute(_CACHE_INSERT, cache_rows)
            for endereco, bairro, lat, lon in pares_ok:
                n += conn.execute(
                    _APPLY, {"endereco": endereco, "bairro": bairro, "lat": lat, "lon": lon}
                ).rowcount
        return n

    # Pares já resolvidos no cache: aplica antes da rede (vale mesmo se a rodada cair).
    if aplicaveis:
        atualizados += flush([], aplicaveis)

    # Consultas novas, com throttle. Erro de rede: pula (sem cache) e segue.
    # Commit a cada _FLUSH_N consultas — 1 req/s é caro demais p/ perder num crash.
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    resolvidos = 0
    sem_resultado = 0
    erros_rede = 0
    _FLUSH_N = 25
    cache_buf: list[dict] = []
    pares_buf: list[tuple[str, str | None, float, float]] = []
    for i, (endereco, bairro, chave, consulta) in enumerate(novos[: args.limit], start=1):
        try:
            ponto = geocode_query(session, consulta)
        except requests.RequestException as exc:
            erros_rede += 1
            print(f"  [rede] {consulta}: {exc.__class__.__name__} (re-tenta na próxima rodada)")
            time.sleep(THROTTLE_S)
            continue
        if ponto is None:
            sem_resultado += 1
            cache_buf.append({"chave": chave, "consulta": consulta, "lat": None, "lon": None, "ok": False})
        else:
            resolvidos += 1
            lat, lon = ponto
            cache_buf.append({"chave": chave, "consulta": consulta, "lat": lat, "lon": lon, "ok": True})
            pares_buf.append((endereco, bairro, lat, lon))
        if len(cache_buf) >= _FLUSH_N:
            atualizados += flush(cache_buf, pares_buf)
            print(f"  ...{i}/{min(len(novos), args.limit)} consultas (parcial commitado)")
            cache_buf, pares_buf = [], []
        time.sleep(THROTTLE_S)

    atualizados += flush(cache_buf, pares_buf)

    print(
        f"rodada: {resolvidos} resolvidos, {sem_resultado} sem resultado, {erros_rede} erros de rede | "
        f"{atualizados} comps ganharam geom (nominatim)"
    )
    restantes = len(novos) - min(len(novos), args.limit)
    if restantes > 0:
        print(f"faltam ~{restantes} consultas novas — rode de novo p/ continuar (cache não repete nada)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
