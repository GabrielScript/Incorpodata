"""Carrega o inventário do BestPlaces (terrenos + casas) em market.anuncios e casa com lotes.

Camada "À venda" do Explorar Mapa. Pipeline:
  1. lê o seed do BestPlaces (já sem duplicados entre portais) e fica com terrenos + casas de venda;
  2. canoniza o bairro na grafia de geo.lotes;
  3. oportunidade: terreno -> hedônico (artifacts/hedonic.json); casa -> AVM LightGBM do
     BestPlaces, se vier o arquivo enriquecido (--enriched, gerado por export_enriched.py);
  4. upsert em market.anuncios (ativo=true, ultimo_visto=now()); o que era desta carga e
     sumiu do seed vira ativo=false (vendido/retirado não fica "à venda" no mapa);
  5. casa anúncio→lote (market.anuncio_lote) — ver match_anuncio_lote.

Uso:
    python -m src.scrapers.load_bestplaces --file <BestPlaces>/scraper/imoveis_jp.json
    python -m src.scrapers.load_bestplaces --file ... --enriched <BestPlaces>/ml/imoveis_enriched.json
    python -m src.scrapers.load_bestplaces --file ... --dry-run     # parseia e resume, sem DB
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

from sqlalchemy import text

from src.scrapers.bestplaces import AnuncioBP, from_record, oportunidade_tier
from src.scrapers.comps import canonical_bairro

ROOT = Path(__file__).resolve().parents[2]
HEDONIC = ROOT / "artifacts" / "hedonic.json"

# σ(log) de referência p/ "confiabilidade" — mesma escala do BestPlaces (1 − σ/0,40).
SIGMA_REF = 0.40
Z_SUSPEITO = 3.0
Z_QUARTIL = 0.6745       # faixa típica = q25–q75 da normal

_UPSERT = text(
    """
    INSERT INTO market.anuncios
      (fonte, fonte_id, url, titulo, preco, area_anunc_m2, bairro_texto, vendedor_tipo,
       lat, lon, geom, tipo, business, quartos, banheiros, suites, vagas, iptu, condominio,
       area_terreno_m2, anunciante_nome, anunciante_creci, loc_aproximada, imagem_url, fontes,
       scraped_at, preco_esperado, preco_esperado_lo, preco_esperado_hi, desconto_pct,
       confiabilidade, suspeito, oportunidade_tier, oportunidade_modelo, logradouro_texto,
       ativo, ultimo_visto)
    VALUES
      (:fonte, :fonte_id, :url, :titulo, :preco, :area_anunc_m2, :bairro, 'imobiliaria',
       :lat, :lon,
       CASE WHEN :lat IS NOT NULL AND :lon IS NOT NULL
            THEN ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 31985) END,
       :tipo, 'SALE', :quartos, :banheiros, :suites, :vagas, :iptu, :condominio,
       :area_terreno_m2, :anunciante_nome, :anunciante_creci, :loc_aproximada, :imagem_url,
       :fontes, CAST(:scraped_at AS timestamptz), :preco_esperado, :preco_esperado_lo,
       :preco_esperado_hi, :desconto_pct, :confiabilidade, :suspeito, :oportunidade_tier,
       :oportunidade_modelo, :logradouro, true, now())
    ON CONFLICT (fonte, fonte_id) DO UPDATE SET
      url = EXCLUDED.url, titulo = EXCLUDED.titulo, preco = EXCLUDED.preco,
      area_anunc_m2 = EXCLUDED.area_anunc_m2, bairro_texto = EXCLUDED.bairro_texto,
      lat = COALESCE(EXCLUDED.lat, market.anuncios.lat),
      lon = COALESCE(EXCLUDED.lon, market.anuncios.lon),
      geom = COALESCE(EXCLUDED.geom, market.anuncios.geom),
      tipo = EXCLUDED.tipo, business = EXCLUDED.business, quartos = EXCLUDED.quartos,
      banheiros = EXCLUDED.banheiros, suites = EXCLUDED.suites, vagas = EXCLUDED.vagas,
      iptu = EXCLUDED.iptu, condominio = EXCLUDED.condominio,
      area_terreno_m2 = EXCLUDED.area_terreno_m2, anunciante_nome = EXCLUDED.anunciante_nome,
      anunciante_creci = EXCLUDED.anunciante_creci, loc_aproximada = EXCLUDED.loc_aproximada,
      imagem_url = EXCLUDED.imagem_url, fontes = EXCLUDED.fontes,
      scraped_at = EXCLUDED.scraped_at, preco_esperado = EXCLUDED.preco_esperado,
      preco_esperado_lo = EXCLUDED.preco_esperado_lo, preco_esperado_hi = EXCLUDED.preco_esperado_hi,
      desconto_pct = EXCLUDED.desconto_pct, confiabilidade = EXCLUDED.confiabilidade,
      suspeito = EXCLUDED.suspeito, oportunidade_tier = EXCLUDED.oportunidade_tier,
      oportunidade_modelo = EXCLUDED.oportunidade_modelo,
      logradouro_texto = EXCLUDED.logradouro_texto, ativo = true, ultimo_visto = now()
    """
)


# ───────────────────────── oportunidade ─────────────────────────
def sigma_hedonico(artifact: dict) -> float:
    """σ(log) do hedônico a partir do MAE-log da CV espacial (normal: σ ≈ 1,2533·MAE)."""
    return 1.2533 * float(artifact["cv_espacial"]["mae_log_modelo"])


def oportunidade_terreno(a: AnuncioBP, artifact: dict) -> dict:
    """Preço esperado do terreno pelo hedônico (mediana condicional × área do lote)."""
    from src.ml.hedonic import predict_m2

    if not (a.lat and a.lon and a.area_terreno_m2 and a.bairro):
        return {}
    m2 = predict_m2(artifact, a.area_terreno_m2, a.lat, a.lon, a.bairro)
    esperado = m2 * a.area_terreno_m2
    return _campos(a.preco, esperado, sigma_hedonico(artifact), "hedonico")


def _campos(preco: float, esperado: float, sigma: float, modelo: str) -> dict:
    if not (esperado and esperado > 0 and preco > 0 and sigma > 0):
        return {}
    g = math.log(esperado) - math.log(preco)          # >0 = pedido abaixo do esperado
    z = g / sigma
    desconto = max(-1.5, min(0.95, (esperado - preco) / esperado))
    conf = max(0.0, min(1.0, 1 - sigma / SIGMA_REF))
    suspeito = abs(z) > Z_SUSPEITO
    return {
        "preco_esperado": esperado,
        "preco_esperado_lo": esperado * math.exp(-Z_QUARTIL * sigma),
        "preco_esperado_hi": esperado * math.exp(Z_QUARTIL * sigma),
        "desconto_pct": desconto,
        "confiabilidade": conf,
        "suspeito": suspeito,
        "oportunidade_tier": oportunidade_tier(desconto, conf, suspeito),
        "oportunidade_modelo": modelo,
    }


def oportunidade_casa(a: AnuncioBP, enriched: dict[str, dict]) -> dict:
    """Campos do AVM do BestPlaces (arquivo enriquecido, chave 'fonte:id')."""
    e = enriched.get(f"{a.fonte}:{a.fonte_id}")
    if not e or not e.get("expected_price"):
        return {}
    desconto = float(e.get("deal_score") or 0.0)
    conf = float(e.get("reliability") or 0.0)
    suspeito = bool(e.get("suspect"))
    return {
        "preco_esperado": e["expected_price"],
        "preco_esperado_lo": e.get("expected_low"),
        "preco_esperado_hi": e.get("expected_high"),
        "desconto_pct": desconto,
        "confiabilidade": conf,
        "suspeito": suspeito,
        "oportunidade_tier": oportunidade_tier(desconto, conf, suspeito),
        "oportunidade_modelo": "lightgbm",
    }


# ───────────────────────── carga ─────────────────────────
def load_records(path: Path) -> list[AnuncioBP]:
    data = json.loads(path.read_text(encoding="utf-8"))
    seen: dict[tuple[str, str], AnuncioBP] = {}
    for r in data:
        a = from_record(r)
        if a:
            seen.setdefault((a.fonte, a.fonte_id), a)
    return list(seen.values())


def canonizar(ans: list[AnuncioBP], canon: dict[str, str]) -> list[AnuncioBP]:
    """Bairro na grafia oficial quando reconhecido (o casamento usa); senão mantém o texto."""
    return [replace(a, bairro=canonical_bairro(a.bairro, canon) or a.bairro) for a in ans]


def rows_for(ans: list[AnuncioBP], artifact: dict | None, enriched: dict[str, dict]) -> list[dict]:
    rows = []
    for a in ans:
        if a.categoria == "terreno" and artifact:
            op = oportunidade_terreno(a, artifact)
        elif a.categoria == "casa":
            op = oportunidade_casa(a, enriched)
        else:
            op = {}
        rows.append({
            "fonte": a.fonte, "fonte_id": a.fonte_id, "url": a.url, "titulo": a.titulo,
            "preco": a.preco, "area_anunc_m2": a.area_anunc_m2, "bairro": a.bairro,
            "logradouro": a.logradouro,
            "lat": a.lat, "lon": a.lon, "tipo": a.tipo, "quartos": a.quartos,
            "banheiros": a.banheiros, "suites": a.suites, "vagas": a.vagas, "iptu": a.iptu,
            "condominio": a.condominio, "area_terreno_m2": a.area_terreno_m2,
            "anunciante_nome": a.anunciante_nome, "anunciante_creci": a.anunciante_creci,
            "loc_aproximada": a.loc_aproximada, "imagem_url": a.imagem_url,
            "fontes": list(a.fontes), "scraped_at": a.scraped_at,
            "preco_esperado": None, "preco_esperado_lo": None, "preco_esperado_hi": None,
            "desconto_pct": None, "confiabilidade": None, "suspeito": None,
            "oportunidade_tier": None, "oportunidade_modelo": None,
            **op,
        })
    return rows


def upsert(rows: list[dict], chunk: int = 500) -> None:
    from src.db.database import get_engine

    with get_engine().begin() as conn:
        for i in range(0, len(rows), chunk):
            conn.execute(_UPSERT, rows[i:i + chunk])
        # Desta carga (scraped_at preenchido) e fora do seed atual = saiu do ar.
        conn.execute(text("CREATE TEMP TABLE _vistos (fonte text, fonte_id text) ON COMMIT DROP"))
        conn.execute(text("INSERT INTO _vistos VALUES (:fonte, :fonte_id)"),
                     [{"fonte": r["fonte"], "fonte_id": r["fonte_id"]} for r in rows])
        n = conn.execute(text(
            """
            UPDATE market.anuncios a SET ativo = false
            WHERE a.ativo AND a.scraped_at IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM _vistos v
                              WHERE v.fonte = a.fonte AND v.fonte_id = a.fonte_id)
            """
        )).rowcount
    print(f"upsert: {len(rows)} anúncios; desativados (saíram do seed): {n}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Inventário BestPlaces -> market.anuncios + casamento")
    ap.add_argument("--file", required=True, help="seed do BestPlaces (imoveis_jp.json)")
    ap.add_argument("--enriched", help="AVM do BestPlaces por anúncio (export_enriched.py)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sem-casamento", action="store_true", help="só carrega, não casa com lotes")
    args = ap.parse_args(argv)

    ans = load_records(Path(args.file))
    cats = Counter(a.categoria for a in ans)
    print(f"terrenos: {cats['terreno']} | casas: {cats['casa']} | "
          f"com coordenada: {sum(1 for a in ans if a.lat)} "
          f"(exata: {sum(1 for a in ans if a.lat and not a.loc_aproximada)}) | "
          f"casa com área de terreno no texto: "
          f"{sum(1 for a in ans if a.categoria == 'casa' and a.area_terreno_m2)}")

    artifact = json.loads(HEDONIC.read_text(encoding="utf-8")) if HEDONIC.exists() else None
    enriched: dict[str, dict] = {}
    if args.enriched:
        enriched = json.loads(Path(args.enriched).read_text(encoding="utf-8"))
        print(f"AVM enriquecido: {len(enriched)} anúncios")

    if not args.dry_run:
        from src.scrapers.load_comps import fetch_bairros_canon

        ans = canonizar(ans, fetch_bairros_canon())
    rows = rows_for(ans, artifact, enriched)
    tiers = Counter(r["oportunidade_tier"] for r in rows)
    print("selos:", dict(tiers))
    if args.dry_run:
        return 0

    upsert(rows)
    if not args.sem_casamento:
        from src.scrapers.match_anuncio_lote import casar

        casar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
