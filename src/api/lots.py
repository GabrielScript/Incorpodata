"""Rotas de lotes: GeoJSON para o mapa + ficha de viabilidade por lote."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.api.db import get_conn
from src.api.pdf import build_ficha_pdf
from src.api.schemas import VGV, Listing, LotFicha, Restricao, Viability
from src.api.viability import altura_label, estimar_vgv

router = APIRouter(prefix="/api", tags=["lots"])

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
                    "sigla": r["sigla"],
                    "a_venda": bool(r["a_venda"]),
                    "preco": _f(r["preco"]),
                    "preco_m2": _f(r["preco_m2"]),
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

    # VGV: envelope (projeção térreo) × R$/m² mediano de APARTAMENTO no bairro (comps de venda).
    # Bairro casado pela mesma normalização das siglas (upper + só A-Z0-9) — dispensa unaccent.
    vgv = None
    prow = conn.execute(
        text(
            """
            SELECT preco_m2_mediana, n
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
    if prow is not None and row["area_projecao_max_m2"] is not None:
        est = estimar_vgv(_f(row["area_projecao_max_m2"]), _f(prow["preco_m2_mediana"]))
        if est is not None:
            vgv = VGV(
                preco_m2_venda=est.preco_m2_venda,
                n_comps=prow["n"],
                eficiencia=est.eficiencia,
                pavimentos=est.pavimentos,
                area_projecao_m2=est.area_projecao_m2,
                area_privativa_pavto_m2=est.area_privativa_pavto_m2,
                vgv_por_pavimento=est.vgv_por_pavimento,
                area_construida_m2=est.area_construida_m2,
                area_privativa_total_m2=est.area_privativa_total_m2,
                vgv_total=est.vgv_total,
                premissas=(
                    f"R$/m² = mediana de {prow['n']} comps de apartamento à venda em "
                    f"{row['bairro']}; eficiência {est.eficiencia:.0%}; "
                    f"{est.pavimentos} pavimentos (premissa — altura é espacial em JP)"
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
        centroid=centroid,
        viability=viability,
        restricao=restricao,
        listing=listing,
        vgv=vgv,
    )


@router.get("/lots/{lot_id}", response_model=LotFicha)
def get_lot(lot_id: int, conn: Connection = Depends(get_conn)) -> LotFicha:
    ficha = _load_ficha(lot_id, conn)
    if ficha is None:
        raise HTTPException(status_code=404, detail="lote não encontrado")
    return ficha


@router.get("/lots/{lot_id}/pdf")
def get_lot_pdf(lot_id: int, conn: Connection = Depends(get_conn)) -> Response:
    """Ficha do lote em PDF (com VGV) — levável ao comitê."""
    ficha = _load_ficha(lot_id, conn)
    if ficha is None:
        raise HTTPException(status_code=404, detail="lote não encontrado")
    pdf = build_ficha_pdf(ficha)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="ficha-lote-{lot_id}.pdf"'},
    )
