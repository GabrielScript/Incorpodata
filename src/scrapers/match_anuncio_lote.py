"""Casa anúncios ativos (market.anuncios) com lotes do cadastro (geo.lotes) -> market.anuncio_lote.

Primeiro decide se o pino do anúncio é EXATO ou APROXIMADO. Aproximado quando:
  - o portal marca (approx_location), ou
  - a fonte não expõe precisão (OLX: pino costuma ser o centróide do CEP), ou
  - o mesmo ponto é compartilhado por 3+ anúncios ativos (centróide de rua/bairro).
Auditoria 2026-09-25: sem essa regra, 3 casas de R$ 0,9–1,3 mi em Muçumagro casavam no
MESMO lote de 215 m² (pino genérico), e "lote mais próximo" errava a área em 5× na mediana.

Métodos, do mais ao menos confiável (score 0–1 = certeza do casamento):
  1. ponto_no_lote — pino exato dentro do polígono. Área anunciada do terreno bate (±25%) →
                     1,0; sem área p/ conferir → 0,85; ±50% → 0,7; pior que isso → rejeita
                     (pino no lote vizinho/gleba) e o anúncio cai no método 3.
  2. ponto_proximo — pino exato na rua: lote mais próximo até 15 m, SÓ com área conferida
                     (±25%). Score 0,6.
  3. area_raio     — pino aproximado (ou exato rejeitado): lotes a até 300 m, mesmo bairro,
                     área ±10% (terreno: só lote vago). Só grava candidato ÚNICO.
                     Score 0,5 × similaridade da área.
Sem candidato = sem casamento (o anúncio segue valendo como comp/estatística).

Idempotente: refaz os casamentos automáticos; 'manual' e 'endereco' são preservados.
Uso: python -m src.scrapers.match_anuncio_lote
"""
from __future__ import annotations

import sys

from sqlalchemy import text

RAIO_APROX_M = 300.0
TOL_AREA_APROX = 0.10
DIST_RUA_M = 15.0
PINO_COMPARTILHADO = 3          # anúncios no mesmo ponto → centróide, não endereço
FONTES_SEM_PRECISAO = ("olx",)


def _sql_in(vals: tuple[str, ...]) -> str:
    """Tupla Python -> lista SQL (repr de 1 item vira "('olx',)", inválido em SQL)."""
    return "(" + ", ".join(f"'{v}'" for v in vals) + ")"

_METODOS_AUTO = ("ponto_no_lote", "ponto_proximo", "area_raio")

# Área relativa: |lote − anunciada| / anunciada (NULL quando o anúncio não traz área de terreno).
_DIF = "abs(l.area_geom_m2 - p.area_terreno_m2) / nullif(p.area_terreno_m2, 0)"

_SQL = [
    ("limpa automáticos", f"""
        DELETE FROM market.anuncio_lote WHERE metodo IN {_sql_in(_METODOS_AUTO)}
    """),
    ("pinos", f"""
        CREATE TEMP TABLE _pinos ON COMMIT DROP AS
        SELECT a.id, a.geom, a.area_terreno_m2, a.bairro_texto,
               (a.tipo ILIKE '%terreno%' OR a.tipo ILIKE '%lote%') AS terreno,
               (coalesce(a.loc_aproximada, false)
                OR a.fonte IN {_sql_in(FONTES_SEM_PRECISAO)}
                OR count(*) OVER (PARTITION BY round(a.lat::numeric, 5), round(a.lon::numeric, 5))
                   >= {PINO_COMPARTILHADO}) AS aprox
        FROM market.anuncios a
        WHERE a.ativo AND a.geom IS NOT NULL
    """),
    ("ponto_no_lote", f"""
        INSERT INTO market.anuncio_lote (anuncio_id, lote_id, metodo, score)
        SELECT DISTINCT ON (p.id) p.id, l.id, 'ponto_no_lote',
               CASE WHEN p.area_terreno_m2 IS NULL THEN 0.85
                    WHEN {_DIF} <= 0.25 THEN 1.0
                    ELSE 0.7 END
        FROM _pinos p
        JOIN geo.lotes l ON ST_Contains(l.geom, p.geom)
        WHERE NOT p.aprox AND (p.area_terreno_m2 IS NULL OR {_DIF} <= 0.5)
        ORDER BY p.id, l.area_geom_m2          -- lote sobreposto: fica o menor (mais específico)
        ON CONFLICT DO NOTHING
    """),
    ("ponto_proximo", f"""
        INSERT INTO market.anuncio_lote (anuncio_id, lote_id, metodo, score)
        SELECT p.id, near.id, 'ponto_proximo', 0.6
        FROM _pinos p
        CROSS JOIN LATERAL (
            SELECT l.id, l.area_geom_m2 FROM geo.lotes l
            WHERE ST_DWithin(l.geom, p.geom, {DIST_RUA_M})
            ORDER BY l.geom <-> p.geom
            LIMIT 1
        ) near
        WHERE NOT p.aprox AND p.area_terreno_m2 > 0
          AND abs(near.area_geom_m2 - p.area_terreno_m2) <= 0.25 * p.area_terreno_m2
          AND NOT EXISTS (SELECT 1 FROM market.anuncio_lote x WHERE x.anuncio_id = p.id)
          AND NOT EXISTS (SELECT 1 FROM geo.lotes l2 WHERE ST_Contains(l2.geom, p.geom))
        ON CONFLICT DO NOTHING
    """),
    ("area_raio", f"""
        WITH cand AS (
            SELECT p.id AS anuncio_id, l.id AS lote_id, {_DIF} AS dif,
                   count(*) OVER (PARTITION BY p.id) AS n
            FROM _pinos p
            JOIN geo.lotes l
              ON ST_DWithin(l.geom, p.geom, {RAIO_APROX_M})
             AND market.unaccent_bairro(l.bairro) = market.unaccent_bairro(p.bairro_texto)
             AND {_DIF} <= {TOL_AREA_APROX}
             AND (NOT p.terreno OR l.tipo = 'TERRITORIAL')
            WHERE p.area_terreno_m2 > 0
              AND NOT EXISTS (SELECT 1 FROM market.anuncio_lote x WHERE x.anuncio_id = p.id)
        )
        INSERT INTO market.anuncio_lote (anuncio_id, lote_id, metodo, score)
        SELECT anuncio_id, lote_id, 'area_raio', round((0.5 * (1 - dif))::numeric, 3)
        FROM cand WHERE n = 1
        ON CONFLICT DO NOTHING
    """),
]


def casar() -> dict[str, int]:
    from src.db.database import get_engine

    out: dict[str, int] = {}
    with get_engine().begin() as conn:
        for nome, sql in _SQL:
            out[nome] = conn.execute(text(sql)).rowcount
        resumo = conn.execute(text(
            """
            SELECT count(*) FILTER (WHERE a.ativo) AS ativos,
                   count(DISTINCT al.anuncio_id) AS casados,
                   count(DISTINCT al.anuncio_id) FILTER (WHERE l.tipo = 'TERRITORIAL') AS em_vago
            FROM market.anuncios a
            LEFT JOIN market.anuncio_lote al ON al.anuncio_id = a.id
            LEFT JOIN geo.lotes l ON l.id = al.lote_id
            """
        )).one()
    print("casamento:", {k: v for k, v in out.items() if k not in ("limpa automáticos", "pinos")},
          f"| ativos {resumo.ativos}, casados {resumo.casados}, em lote vago {resumo.em_vago}")
    return out


if __name__ == "__main__":
    casar()
    sys.exit(0)
