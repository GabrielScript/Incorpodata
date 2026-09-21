"""Rotas de lotes: GeoJSON para o mapa + ficha de viabilidade por lote."""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.api.auth import get_current_plan, get_optional_plan
from src.api.db import get_conn
from src.api.pdf import build_ficha_pdf
from src.api.plans import limits_for
from src.api.schemas import (
    VGV,
    Listing,
    LotFicha,
    Oportunidade,
    Residual,
    Restricao,
    Score,
    Viability,
)
from src.api.viability import (
    AREA_LOTE_SUSPEITA_M2,
    PrecoStats,
    altura_label,
    aviso_area_grande,
    escolher_preco_ref,
    estimar_residual,
    estimar_vgv,
    geometria_suspeita,
    incorpo_score,
)

router = APIRouter(prefix="/api", tags=["lots"])

# Camada "à venda" (market.anuncios) DESLIGADA por default: sem scraper agendado o anúncio
# envelhece e um lote "à venda" já vendido queima credibilidade. Schema, scraper e casamento
# continuam existindo; religar = ANUNCIOS_ATIVOS=1 quando houver frescor garantido.
ANUNCIOS_ATIVOS = os.getenv("ANUNCIOS_ATIVOS", "0").strip().lower() in {"1", "true", "sim"}

# Raio (m, SRID 31985) p/ a mediana de R$/m² na MICRO-localização do lote. Mediana do bairro
# inteiro mascara variância intra-bairro (frente-mar × fundo); só caímos nela se o raio for ralo.
RAIO_COMPS_M = 800.0

# Ordenações permitidas pelas variáveis que importam na originação de terreno:
# tamanho do lote, o que cabe no térreo, preço e preço/m² (barganha). As chaves são a
# allowlist — o pattern do Query é derivado delas, então nada fora daqui chega ao SQL
# (seguro injetar). `, l.id` no fim = desempate estável (lista não "pula" ao reordenar).
_ORDER = {
    "none": "l.id",
    "area_desc": "l.area_geom_m2 DESC NULLS LAST, l.id",
    "area_asc": "l.area_geom_m2 ASC NULLS LAST, l.id",
    "proj_desc": "lz.area_projecao_max_m2 DESC NULLS LAST, l.id",
    "proj_asc": "lz.area_projecao_max_m2 ASC NULLS LAST, l.id",
    "preco_asc": "al.preco ASC NULLS LAST, l.id",
    "preco_desc": "al.preco DESC NULLS LAST, l.id",
    "preco_m2_asc": "al.preco_m2 ASC NULLS LAST, l.id",
    "preco_m2_desc": "al.preco_m2 DESC NULLS LAST, l.id",
}
_SORT_PATTERN = "^(" + "|".join(_ORDER) + ")$"


def _f(v: object) -> float | None:
    """Decimal/None -> float/None (Pydantic aceita, JSON serializa)."""
    return float(v) if v is not None else None  # type: ignore[arg-type]


@router.get("/bairros")
def list_bairros(conn: Connection = Depends(get_conn)) -> list[str]:
    rows = conn.execute(
        text("SELECT DISTINCT bairro FROM geo.lotes WHERE bairro IS NOT NULL ORDER BY bairro")
    ).all()
    return [r[0] for r in rows]


@router.get("/lots")
def list_lots(
    bairro: str = Query("", description="filtro de bairro (ILIKE); '' = todos"),
    only_vacant: bool = Query(True, description="só lotes TERRITORIAL (vagos) — alvo do negócio"),
    a_venda: bool = Query(False, description="só lotes com anúncio casado"),
    area_min: float | None = Query(None, ge=0, description="área mínima do lote (m²)"),
    area_max: float | None = Query(None, ge=0, description="área máxima do lote (m²)"),
    sort: str = Query("none", pattern=_SORT_PATTERN, description="ordenação (ver _ORDER)"),
    limit: int = Query(2000, le=10000),
    conn: Connection = Depends(get_conn),
) -> dict:
    """Lotes como GeoJSON FeatureCollection (geom reprojetada 31985 -> 4326)."""
    sql = f"""
        SELECT l.id, l.logradouro, l.bairro, l.tipo, l.area_geom_m2, lz.sigla,
               lz.area_projecao_max_m2,
               (al.anuncio_id IS NOT NULL) AS a_venda, al.preco, al.preco_m2,
               ST_AsGeoJSON(ST_Transform(l.geom, 4326)) AS geojson
        FROM geo.lotes l
        LEFT JOIN geo.lote_zona lz ON lz.lote_id = l.id
        LEFT JOIN LATERAL (
            SELECT a.id AS anuncio_id, a.preco, a.preco_m2
            FROM market.anuncio_lote al2
            JOIN market.anuncios a ON a.id = al2.anuncio_id AND a.ativo
            WHERE al2.lote_id = l.id
            ORDER BY al2.score DESC NULLS LAST
            LIMIT 1
        ) al ON true
        WHERE (:bairro = '' OR l.bairro ILIKE :bairro)
          AND (NOT :only_vacant OR l.tipo = 'TERRITORIAL')
          AND (NOT :a_venda OR al.anuncio_id IS NOT NULL)
          AND (:area_min IS NULL OR l.area_geom_m2 >= :area_min)
          AND (:area_max IS NULL OR l.area_geom_m2 <= :area_max)
        ORDER BY {_ORDER[sort]}
        LIMIT :limit
    """
    rows = conn.execute(
        text(sql),
        {
            "bairro": bairro,
            "only_vacant": only_vacant,
            "a_venda": a_venda,
            "area_min": area_min,
            "area_max": area_max,
            "limit": limit,
        },
    ).mappings().all()

    features = []
    for r in rows:
        if not r["geojson"]:
            continue
        features.append(
            {
                "type": "Feature",
                "id": r["id"],
                "geometry": json.loads(r["geojson"]),
                "properties": {
                    "id": r["id"],
                    "logradouro": r["logradouro"],
                    "bairro": r["bairro"],
                    "tipo": r["tipo"],
                    "area_m2": _f(r["area_geom_m2"]),
                    "area_projecao_max_m2": _f(r["area_projecao_max_m2"]),
                    "geometria_suspeita": geometria_suspeita(_f(r["area_geom_m2"])),
                    "sigla": r["sigla"],
                    "a_venda": bool(r["a_venda"]) and ANUNCIOS_ATIVOS,
                    "preco": _f(r["preco"]) if ANUNCIOS_ATIVOS else None,
                    "preco_m2": _f(r["preco_m2"]) if ANUNCIOS_ATIVOS else None,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _load_ficha(lot_id: int, conn: Connection) -> LotFicha | None:
    """Ficha completa do lote (cadastro + viabilidade + restrição + anúncio + VGV). None se não existe."""
    sql = """
        SELECT l.id, l.inscricao, l.setor, l.quadra, l.lote, l.logradouro,
               l.bairro, l.tipo, l.area_cad_m2, l.area_geom_m2,
               ST_X(ST_Transform(ST_PointOnSurface(l.geom), 4326)) AS lng,
               ST_Y(ST_Transform(ST_PointOnSurface(l.geom), 4326)) AS lat,
               lz.sigla, p.nome AS nome_zona, p.to_max_pct, p.tap_min_pct,
               p.recuo_frontal_m, p.recuo_lateral, p.recuo_fundo, p.usos_obs,
               lz.area_projecao_max_m2, lz.area_permeavel_min_m2,
               lr.faixa_orla, lr.em_centro_historico, lr.em_barreira, lr.altura_livre
        FROM geo.lotes l
        LEFT JOIN geo.lote_zona lz ON lz.lote_id = l.id
        LEFT JOIN zoning.parametros p
               ON regexp_replace(upper(p.sigla),  '[^A-Z0-9]', '', 'g')
                = regexp_replace(upper(lz.sigla), '[^A-Z0-9]', '', 'g')
        LEFT JOIN geo.lote_restricao lr ON lr.lote_id = l.id
        WHERE l.id = :id
    """
    row = conn.execute(text(sql), {"id": lot_id}).mappings().first()
    if row is None:
        return None

    lrow = None
    if ANUNCIOS_ATIVOS:
        lrow = conn.execute(
            text(
                """
                SELECT a.id AS anuncio_id, a.fonte, a.preco, a.area_anunc_m2, a.preco_m2
                FROM market.anuncio_lote al
                JOIN market.anuncios a ON a.id = al.anuncio_id AND a.ativo
                WHERE al.lote_id = :id
                ORDER BY al.score DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"id": lot_id},
        ).mappings().first()

    viability = None
    if row["sigla"] is not None:
        viability = Viability(
            sigla=row["sigla"],
            nome_zona=row["nome_zona"],
            to_max_pct=_f(row["to_max_pct"]),
            tap_min_pct=_f(row["tap_min_pct"]),
            area_projecao_max_m2=_f(row["area_projecao_max_m2"]),
            area_permeavel_min_m2=_f(row["area_permeavel_min_m2"]),
            recuo_frontal_m=_f(row["recuo_frontal_m"]),
            recuo_lateral=row["recuo_lateral"],
            recuo_fundo=row["recuo_fundo"],
            usos_obs=row["usos_obs"],
        )

    em_ch = bool(row["em_centro_historico"]) if row["em_centro_historico"] is not None else False
    em_bar = bool(row["em_barreira"]) if row["em_barreira"] is not None else False
    restricao = Restricao(
        faixa_orla=row["faixa_orla"],
        em_centro_historico=em_ch,
        em_barreira=em_bar,
        altura_livre=row["altura_livre"],
        altura_label=altura_label(row["faixa_orla"], em_ch, em_bar, row["altura_livre"]),
    )

    listing = None
    if lrow is not None:
        listing = Listing(
            anuncio_id=lrow["anuncio_id"],
            fonte=lrow["fonte"],
            preco=_f(lrow["preco"]),
            area_anunc_m2=_f(lrow["area_anunc_m2"]),
            preco_m2=_f(lrow["preco_m2"]),
        )

    # VGV: envelope (projeção térreo) × R$/m² mediano de APARTAMENTO (comps de venda).
    # Preferimos a mediana dos comps no RAIO do lote (micro-localização); caímos no bairro
    # quando o raio tem poucos comps. Faixa Q1–Q3 explícita p/ não fingir precisão de ponto.
    vgv = None
    residual = None
    score = None
    raio_row = conn.execute(
        text(
            """
            SELECT
              percentile_cont(0.5)  WITHIN GROUP (ORDER BY c.preco_m2) AS mediana,
              percentile_cont(0.25) WITHIN GROUP (ORDER BY c.preco_m2) AS q1,
              percentile_cont(0.75) WITHIN GROUP (ORDER BY c.preco_m2) AS q3,
              count(*) AS n
            FROM market.comps c, geo.lotes l
            WHERE l.id = :id
              AND c.tipo = 'Apartamento' AND c.business = 'SALE'
              AND c.geom IS NOT NULL
              -- pino aproximado de portal (dezenas de anúncios no mesmo ponto) distorce a
              -- mediana espacial: fora do raio; segue valendo p/ a mediana de bairro (view)
              AND c.geo_fonte IS DISTINCT FROM 'fonte_aprox'
              AND c.preco_m2 BETWEEN 800 AND 30000
              AND ST_DWithin(c.geom, l.geom, :raio_m)
            """
        ),
        {"id": lot_id, "raio_m": RAIO_COMPS_M},
    ).mappings().first()
    # Mesma normalização das siglas (upper + só A-Z0-9) — dispensa unaccent.
    prow = conn.execute(
        text(
            """
            SELECT preco_m2_mediana, preco_m2_q1, preco_m2_q3, n
            FROM market.preco_m2_bairro
            WHERE tipo = 'Apartamento'
              AND regexp_replace(upper(bairro),  '[^A-Z0-9]', '', 'g')
                = regexp_replace(upper(:bairro), '[^A-Z0-9]', '', 'g')
            ORDER BY n DESC
            LIMIT 1
            """
        ),
        {"bairro": row["bairro"] or ""},
    ).mappings().first()

    raio_stats = None
    if raio_row is not None and raio_row["n"] and raio_row["mediana"] is not None:
        raio_stats = PrecoStats(
            _f(raio_row["mediana"]), _f(raio_row["q1"]), _f(raio_row["q3"]), int(raio_row["n"])
        )
    bairro_stats = None
    if prow is not None and prow["preco_m2_mediana"] is not None:
        bairro_stats = PrecoStats(
            _f(prow["preco_m2_mediana"]), _f(prow["preco_m2_q1"]), _f(prow["preco_m2_q3"]), int(prow["n"])
        )

    # Guarda de plausibilidade: gleba/ZEPA NÃO recebe VGV (área × TO% × R$/m² numa área de
    # hectares cospe bilhões sem sentido). O aviso diz por quê, conforme a zona.
    suspeita = geometria_suspeita(_f(row["area_geom_m2"]))
    geometria_aviso = aviso_area_grande(_f(row["area_geom_m2"]), row["sigla"])

    ref = escolher_preco_ref(raio_stats, bairro_stats)
    if ref is not None and row["area_projecao_max_m2"] is not None and not suspeita:
        est = estimar_vgv(
            _f(row["area_projecao_max_m2"]), ref.preco_m2,
            preco_m2_q1=ref.q1, preco_m2_q3=ref.q3,
        )
        if est is not None:
            origem = (
                f"comps de apartamento à venda num raio de {RAIO_COMPS_M:.0f} m do lote"
                if ref.fonte == "raio"
                else f"comps de apartamento à venda em {row['bairro']} (raio sem comps suficientes)"
            )
            vgv = VGV(
                preco_m2_venda=est.preco_m2_venda,
                preco_m2_q1=ref.q1,
                preco_m2_q3=ref.q3,
                n_comps=ref.n,
                fonte_preco=ref.fonte,
                eficiencia=est.eficiencia,
                pavimentos=est.pavimentos,
                area_projecao_m2=est.area_projecao_m2,
                area_privativa_pavto_m2=est.area_privativa_pavto_m2,
                vgv_por_pavimento=est.vgv_por_pavimento,
                vgv_por_pavimento_min=est.vgv_por_pavimento_min,
                vgv_por_pavimento_max=est.vgv_por_pavimento_max,
                area_construida_m2=est.area_construida_m2,
                area_privativa_total_m2=est.area_privativa_total_m2,
                vgv_total=est.vgv_total,
                vgv_total_min=est.vgv_total_min,
                vgv_total_max=est.vgv_total_max,
                premissas=(
                    f"R$/m² = mediana de {ref.n} {origem} (faixa Q1–Q3); "
                    f"eficiência {est.eficiencia:.0%}; {est.pavimentos} pavimentos "
                    f"(premissa — altura é espacial em JP). VGV preliminar."
                ),
            )

            # Valor residual ("quanto pagar"): inverte o VGV pela margem-alvo. Usa o preço
            # pedido do anúncio (quando casado) p/ o gap de barganha. Mesmas guardas do VGV.
            res = estimar_residual(est, preco_pedido=listing.preco if listing else None)
            residual = Residual(
                custo_obra_m2=res.custo_obra_m2,
                margem_alvo=res.margem_alvo,
                custos_indiretos_pct=res.custos_indiretos_pct,
                residual_por_pavimento=res.residual_por_pavimento,
                residual_por_pavimento_min=res.residual_por_pavimento_min,
                residual_por_pavimento_max=res.residual_por_pavimento_max,
                residual_total=res.residual_total,
                residual_total_min=res.residual_total_min,
                residual_total_max=res.residual_total_max,
                terreno_pct_vgv=res.terreno_pct_vgv,
                preco_pedido=res.preco_pedido,
                gap_pct=res.gap_pct,
                cabe_no_bolso=res.cabe_no_bolso,
                premissas=(
                    f"Máximo a pagar p/ margem-alvo de {res.margem_alvo:.0%}. Custo de obra "
                    f"R$ {res.custo_obra_m2:.0f}/m² (premissa — calibrar ao CUB-PB) + "
                    f"{res.custos_indiretos_pct:.0%} de custos sobre o VGV. "
                    f"Método involutivo, preliminar."
                ),
            )

            # IncorpoScore: nota 0–100 de atratividade (4 eixos). Reusa VGV+residual+comps já
            # calculados; a guarda de suspeita/zona já garante que só chega aqui lote ranqueável.
            sb = incorpo_score(
                vgv_por_pavimento=est.vgv_por_pavimento,
                area_lote_m2=_f(row["area_geom_m2"]) or 0.0,
                preco_m2=ref.preco_m2,
                n_comps=ref.n,
                terreno_pct_vgv=res.terreno_pct_vgv,
                gap_pct=res.gap_pct,
                q1=ref.q1,
                q3=ref.q3,
                em_centro_historico=em_ch,
                em_barreira=em_bar,
            )
            score = Score(
                total=sb.total,
                rentabilidade=sb.rentabilidade,
                aproveitamento=sb.aproveitamento,
                localizacao=sb.localizacao,
                confianca=sb.confianca,
                penalidade_altura=sb.penalidade_altura,
                nota_metodo=(
                    "Nota relativa às premissas e às âncoras de JP — preliminar. Ordena "
                    "oportunidades; não sobrepõe a análise legal/altura nem substitui avaliação."
                ),
            )

    centroid = [row["lng"], row["lat"]] if row["lng"] is not None else None
    return LotFicha(
        id=row["id"],
        inscricao=row["inscricao"],
        setor=row["setor"],
        quadra=row["quadra"],
        lote=row["lote"],
        logradouro=row["logradouro"],
        bairro=row["bairro"],
        tipo=row["tipo"],
        area_cad_m2=_f(row["area_cad_m2"]),
        area_geom_m2=_f(row["area_geom_m2"]),
        geometria_suspeita=suspeita,
        geometria_aviso=geometria_aviso,
        centroid=centroid,
        viability=viability,
        restricao=restricao,
        listing=listing,
        vgv=vgv,
        residual=residual,
        score=score,
    )


@router.get("/lots/{lot_id}", response_model=LotFicha)
def get_lot(
    lot_id: int,
    plano: str = Depends(get_optional_plan),
    conn: Connection = Depends(get_conn),
) -> LotFicha:
    ficha = _load_ficha(lot_id, conn)
    if ficha is None:
        raise HTTPException(status_code=404, detail="lote não encontrado")
    # Gate freemium: tier sem vgv_detalhado vê a ficha, mas VGV e residual viram teaser
    # bloqueado (são as saídas de DECISÃO — "quanto vende" e "quanto pagar").
    if not limits_for(plano).vgv_detalhado:
        if ficha.vgv is not None:
            ficha.vgv = None
            ficha.vgv_bloqueado = True
        if ficha.residual is not None:
            ficha.residual = None
            ficha.residual_bloqueado = True
        if ficha.score is not None:
            ficha.score = None
            ficha.score_bloqueado = True
    return ficha


@router.get("/oportunidades", response_model=list[Oportunidade])
def list_oportunidades(
    bairro: str = Query("", description="filtro de bairro (ILIKE); '' = todos"),
    limit: int = Query(20, ge=1, le=100, description="top-N retornado"),
    cohort_max: int = Query(120, ge=1, le=300, description="teto de lotes avaliados (custo)"),
    # Freemium, não exige token: com PLANS_ENFORCED desligado (demo) o anônimo enxerga tudo;
    # ligado, anônimo cai em free e leva 402 no gate abaixo — a regra de negócio fica intacta.
    plano: str = Depends(get_optional_plan),
    conn: Connection = Depends(get_conn),
) -> list[Oportunidade]:
    """Ranking das melhores oportunidades do recorte por VALOR RESIDUAL. Feature paga.

    Ordena por `residual_total` (quanto vale pagar pelo terreno) — critério transparente que
    o incorporador confere de cabeça. O IncorpoScore segue calculado e devolvido, mas não
    ordena: sem anúncio casado, 3 dos 4 eixos são quase só o preço/m² do bairro relido.
    Avalia (VGV+residual) até `cohort_max` lotes vagos do bairro e devolve os `limit`
    melhores. Custo O(cohort) em queries — caminho de escala: materializar geo.lote_score.
    """
    if not limits_for(plano).vgv_detalhado:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            "ranking de oportunidades disponível nos planos pagos",
        )
    cand = conn.execute(
        text(
            """
            SELECT l.id
            FROM geo.lotes l
            JOIN geo.lote_zona lz ON lz.lote_id = l.id
            WHERE (:bairro = '' OR l.bairro ILIKE :bairro)
              AND l.tipo = 'TERRITORIAL'
              AND lz.area_projecao_max_m2 IS NOT NULL
              AND (l.area_geom_m2 IS NULL OR l.area_geom_m2 < :area_suspeita)
            ORDER BY lz.area_projecao_max_m2 DESC NULLS LAST
            LIMIT :cohort_max
            """
        ),
        {"bairro": bairro, "area_suspeita": AREA_LOTE_SUSPEITA_M2, "cohort_max": cohort_max},
    ).all()

    ops: list[Oportunidade] = []
    for (lot_id,) in cand:
        ficha = _load_ficha(lot_id, conn)
        if ficha is None or ficha.score is None or ficha.vgv is None or ficha.residual is None:
            continue
        ops.append(
            Oportunidade(
                lot_id=ficha.id,
                logradouro=ficha.logradouro,
                bairro=ficha.bairro,
                area_m2=ficha.area_geom_m2,
                vgv_total=ficha.vgv.vgv_total,
                residual_total=ficha.residual.residual_total,
                terreno_pct_vgv=ficha.residual.terreno_pct_vgv,
                gap_pct=ficha.residual.gap_pct,
                cabe_no_bolso=ficha.residual.cabe_no_bolso,
                score=ficha.score,
            )
        )
    ops.sort(key=lambda o: o.residual_total, reverse=True)
    return ops[:limit]


@router.get("/lots/{lot_id}/pdf")
def get_lot_pdf(
    lot_id: int,
    plano: str = Depends(get_optional_plan),  # freemium: ver nota em list_oportunidades
    conn: Connection = Depends(get_conn),
) -> Response:
    """Ficha do lote em PDF (com VGV) — levável ao comitê. Feature paga."""
    if limits_for(plano).pdf_mes == 0:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "ficha em PDF disponível nos planos pagos")
    ficha = _load_ficha(lot_id, conn)
    if ficha is None:
        raise HTTPException(status_code=404, detail="lote não encontrado")
    pdf = build_ficha_pdf(ficha)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="ficha-lote-{lot_id}.pdf"'},
    )
