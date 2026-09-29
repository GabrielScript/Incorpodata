"""Atualiza geo.lotes com uma nova versão do cadastro do Filipeia, preservando os ids.

Diferente do transform_filipeia.sql (TRUNCATE + INSERT, ids novos), aqui o lote é casado
pela inscrição (CODI_CART): o que não mudou fica intacto, o que mudou é atualizado no lugar,
o que é novo entra e o que saiu do cadastro sai. Ids estáveis importam: o landbank vive no
localStorage do navegador por id, e links/fichas apontam para o id.

Fontes:
  --zip data/raw/Lotes.zip   shapefile do portal de download (manual: o portal fica atrás de
                             WAF e bloqueia robôs). É a fonte MAIS ATUAL.
  --wfs                      GeoServer público do Filipeia. Em 09/2026 era um recorte MAIS
                             VELHO que o portal (faltavam ~9 mil lotes reais, com edificação
                             em cima) — as travas abaixo barram a carga nesse estado.

Padrão é simulação: lê, valida, mostra o diff e grava o relatório em data/sync/. Só escreve
no banco com --aplicar (numa transação só). --forcar ignora as travas.

    python -m src.ingest.sync_lotes --zip data/raw/Lotes.zip
    python -m src.ingest.sync_lotes --zip data/raw/Lotes.zip --aplicar
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from src.db.database import INTERNAL_SRID, get_engine
from src.ingest.filipeia_wfs import baixar_camada

ROOT = Path(__file__).resolve().parents[2]
TIPOS_VALIDOS = frozenset({"TERRITORIAL", "PREDIAL"})

# Travas: uma base nova que encolhe ou perde lote demais é quase sempre recorte velho ou
# download pela metade — não um cadastro que mudou.
VARIACAO_TOTAL_MAX = 0.05
REMOVIDOS_MAX = 0.02
FRACAO_VAGOS = (0.05, 0.25)
SEM_BAIRRO_MAX = 0.02
# Geometria "mudou" se a diferença simétrica passa de 1 m² (ruído de ponto flutuante fica fora).
GEOM_TOLERANCIA_M2 = 1.0

COLS = ["inscricao", "logradouro", "tipo", "bairro"]


# ───────────────────────────── leitura e normalização ─────────────────────────────


def _poligonal(geom: shapely.Geometry | None) -> shapely.Geometry | None:
    """MultiPolygon 2D válido (make_valid pode devolver GeometryCollection com linhas)."""
    if geom is None or geom.is_empty:
        return None
    geom = shapely.make_valid(shapely.force_2d(geom))
    if geom.geom_type == "GeometryCollection":
        polys = [g for g in shapely.get_parts(geom) if g.geom_type in ("Polygon", "MultiPolygon")]
        geom = shapely.union_all(polys) if polys else None
    if geom is None or geom.is_empty:
        return None
    return shapely.MultiPolygon([geom]) if geom.geom_type == "Polygon" else geom


def normalizar(bruto: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Colunas do Filipeia (CODI_CART, DESC_LOGR, TIPO_IMOVE) → inscricao/logradouro/tipo."""
    cols = {c.lower(): c for c in bruto.columns}
    faltando = {"codi_cart", "desc_logr", "tipo_imove"} - cols.keys()
    if faltando:
        raise ValueError(f"camada de lotes sem as colunas {sorted(faltando)}; tem {list(bruto.columns)}")
    if bruto.crs is None:
        raise ValueError("camada de lotes sem CRS (.prj ausente)")

    def _txt(col: str) -> pd.Series:
        s = bruto[cols[col]].astype("string").str.strip()
        return s.mask(s == "")

    out = gpd.GeoDataFrame(
        {
            "inscricao": _txt("codi_cart"),
            "logradouro": _txt("desc_logr"),
            "tipo": _txt("tipo_imove").str.upper(),
        },
        geometry=bruto.geometry.values,
        crs=bruto.crs,
    ).to_crs(epsg=INTERNAL_SRID)
    geoms = shapely.make_valid(shapely.force_2d(out.geometry.to_numpy()))
    multi = shapely.get_type_id(geoms) == shapely.GeometryType.MULTIPOLYGON
    out["geometry"] = [g if ok else _poligonal(g) for g, ok in zip(geoms, multi)]
    return out[out["inscricao"].notna() & out.geometry.notna()].reset_index(drop=True)


def atribuir_bairro(lotes: gpd.GeoDataFrame, bairros: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Bairro pelo ponto interno do lote (mesma regra do transform_filipeia.sql)."""
    nome = next(c for c in bairros.columns if c.lower() == "n_bairro")
    b = bairros[[nome, "geometry"]].rename(columns={nome: "bairro"}).to_crs(epsg=INTERNAL_SRID)
    pts = gpd.GeoDataFrame(geometry=lotes.representative_point(), crs=lotes.crs)
    hit = gpd.sjoin(pts, b, predicate="within", how="left")
    hit = hit[~hit.index.duplicated(keep="first")]
    return lotes.assign(bairro=hit["bairro"].astype("string").reindex(lotes.index))


def ler_zip(path: Path) -> gpd.GeoDataFrame:
    return gpd.read_file(path)


def ler_wfs() -> gpd.GeoDataFrame:
    return baixar_camada("Lotes", ["CODI_CART", "DESC_LOGR", "TIPO_IMOVE"])


# ───────────────────────────── diff e travas ─────────────────────────────


@dataclass
class Diff:
    novos: list[str] = field(default_factory=list)
    removidos: list[str] = field(default_factory=list)
    alterados: list[str] = field(default_factory=list)
    # Inscrição repetida (em qualquer das bases) não dá pra casar 1:1 → se o conjunto de
    # linhas dela mudou, apaga e reinsere (ids dessas mudam); se não mudou, fica intacta.
    duplicadas: list[str] = field(default_factory=list)
    detalhe: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def apagar(self) -> list[str]:
        return self.removidos + self.duplicadas

    @property
    def inserir(self) -> list[str]:
        return self.novos + self.duplicadas


def _assinaturas(df: gpd.GeoDataFrame, inscricoes: set[str]) -> dict[str, tuple[tuple[str, ...], ...]]:
    """Por inscrição: conjunto (ordenado) de geometria normalizada + atributos das suas linhas."""
    sub = df[df["inscricao"].isin(inscricoes)]
    wkb = shapely.to_wkb(shapely.normalize(shapely.set_precision(sub.geometry.to_numpy(), 1e-3)), hex=True)
    linhas: dict[str, list[tuple[str, ...]]] = {}
    for insc, g, *attrs in zip(sub["inscricao"], wkb, *(sub[c].fillna("").astype(str) for c in COLS[1:])):
        linhas.setdefault(insc, []).append((g, *attrs))
    return {k: tuple(sorted(v)) for k, v in linhas.items()}


def calcular_diff(atual: gpd.GeoDataFrame, novo: gpd.GeoDataFrame) -> Diff:
    """Compara por inscrição. Ambos com colunas COLS + geometry no mesmo CRS."""
    dup = set(atual.loc[atual["inscricao"].duplicated(keep=False), "inscricao"]) | set(
        novo.loc[novo["inscricao"].duplicated(keep=False), "inscricao"]
    )
    sa, sn = _assinaturas(atual, dup), _assinaturas(novo, dup)
    dup_mudou = sorted(i for i in dup if sa.get(i) != sn.get(i))
    a = atual[~atual["inscricao"].isin(dup)].set_index("inscricao")
    n = novo[~novo["inscricao"].isin(dup)].set_index("inscricao")

    comuns = a.index.intersection(n.index)
    ga, gn = a.geometry.loc[comuns].to_numpy(), n.geometry.loc[comuns].to_numpy()
    iguais = shapely.equals_exact(ga, gn, tolerance=1e-3)
    geom = ~iguais
    geom[geom] = shapely.area(shapely.symmetric_difference(ga[geom], gn[geom])) > GEOM_TOLERANCIA_M2

    mud = pd.DataFrame({"geom": geom}, index=comuns)
    for c in ("tipo", "logradouro", "bairro"):
        mud[c] = a.loc[comuns, c].fillna("").astype(str).values != n.loc[comuns, c].fillna("").astype(str).values
    alterados = mud[mud.any(axis=1)]

    novos = n.index.difference(a.index)
    removidos = a.index.difference(n.index)
    linhas = [
        pd.DataFrame({"inscricao": novos, "acao": "novo", "tipo_depois": n.loc[novos, "tipo"].values}),
        pd.DataFrame({"inscricao": removidos, "acao": "removido", "tipo_antes": a.loc[removidos, "tipo"].values}),
        pd.DataFrame({
            "inscricao": alterados.index, "acao": "alterado",
            "tipo_antes": a.loc[alterados.index, "tipo"].values,
            "tipo_depois": n.loc[alterados.index, "tipo"].values,
            "mudou": ["+".join(c for c, m in linha.items() if m) for linha in alterados.to_dict("records")],
        }),
        pd.DataFrame({"inscricao": dup_mudou, "acao": "duplicada"}),
    ]
    return Diff(
        novos=list(novos), removidos=list(removidos), alterados=list(alterados.index),
        duplicadas=dup_mudou, detalhe=pd.concat(linhas, ignore_index=True),
    )


def validar(n_atual: int, novo: gpd.GeoDataFrame, diff: Diff) -> list[str]:
    """Motivos para NÃO aplicar. Lista vazia = pode aplicar."""
    problemas: list[str] = []
    if novo.empty:
        return ["base nova vazia"]
    tipos = set(novo["tipo"].dropna()) - TIPOS_VALIDOS
    if tipos:
        problemas.append(f"TIPO_IMOVE desconhecido: {sorted(tipos)}")
    if n_atual:
        var = len(novo) / n_atual - 1
        if abs(var) > VARIACAO_TOTAL_MAX:
            problemas.append(f"total de lotes variou {var:+.1%} ({n_atual} → {len(novo)}); "
                             f"limite ±{VARIACAO_TOTAL_MAX:.0%}")
        rem = len(diff.removidos) / n_atual
        if rem > REMOVIDOS_MAX:
            problemas.append(f"{len(diff.removidos)} lotes sairiam ({rem:.1%}); limite {REMOVIDOS_MAX:.0%}")
    vagos = (novo["tipo"] == "TERRITORIAL").mean()
    if not FRACAO_VAGOS[0] <= vagos <= FRACAO_VAGOS[1]:
        problemas.append(f"fração de vagos {vagos:.1%} fora de {FRACAO_VAGOS[0]:.0%}–{FRACAO_VAGOS[1]:.0%}")
    sem_bairro = novo["bairro"].isna().mean()
    if sem_bairro > SEM_BAIRRO_MAX:
        problemas.append(f"{sem_bairro:.1%} dos lotes sem bairro; limite {SEM_BAIRRO_MAX:.0%}")
    return problemas


# ───────────────────────────── escrita ─────────────────────────────

_SQL_ZONA = """
INSERT INTO geo.lote_zona (lote_id, sigla, area_lote_m2, area_projecao_max_m2, area_permeavel_min_m2)
SELECT z.lote_id, z.sigla, z.area_lote_m2,
       z.area_lote_m2 * (p.to_max_pct  / 100.0),
       z.area_lote_m2 * (p.tap_min_pct / 100.0)
FROM (
  SELECT DISTINCT ON (l.id) l.id AS lote_id, l.area_geom_m2 AS area_lote_m2, zo.sigla
  FROM geo.lotes l JOIN geo.zonas zo ON ST_Intersects(l.geom, zo.geom)
  WHERE l.id = ANY(CAST(:ids AS bigint[]))
  ORDER BY l.id, ST_Area(ST_Intersection(l.geom, zo.geom)) DESC
) z
LEFT JOIN zoning.parametros p
  ON regexp_replace(upper(p.sigla), '[^A-Z0-9]', '', 'g')
   = regexp_replace(upper(z.sigla), '[^A-Z0-9]', '', 'g')
"""  # mesma regra de sql/buildability.sql, restrita aos lotes tocados

_SQL_RESTRICAO = """
INSERT INTO geo.lote_restricao (lote_id, faixa_orla, em_centro_historico, em_barreira, altura_livre)
SELECT l.id,
       max(rf.rotulo) FILTER (WHERE rf.tipo = 'faixa_orla'),
       COALESCE(bool_or(rf.tipo = 'centro_historico'), false),
       COALESCE(bool_or(rf.tipo = 'barreira_cabo_branco'), false),
       max(rf.rotulo) FILTER (WHERE rf.tipo = 'faixa_orla') IS NULL
         AND NOT COALESCE(bool_or(rf.tipo IN ('centro_historico', 'barreira_cabo_branco')), false)
FROM geo.lotes l
LEFT JOIN geo.restricao_altura rf ON ST_Contains(rf.geom, ST_PointOnSurface(l.geom))
WHERE l.id = ANY(CAST(:ids AS bigint[]))
GROUP BY l.id
"""  # mesma regra de sql/altura.sql, restrita aos lotes tocados


def _recalcular_derivados(conn: Connection, ids: list[int]) -> None:
    if not ids:
        return
    p = {"ids": ids}
    conn.execute(text("DELETE FROM geo.lote_zona WHERE lote_id = ANY(CAST(:ids AS bigint[]))"), p)
    conn.execute(text(_SQL_ZONA), p)
    conn.execute(text("DELETE FROM geo.lote_restricao WHERE lote_id = ANY(CAST(:ids AS bigint[]))"), p)
    conn.execute(text(_SQL_RESTRICAO), p)


def aplicar(engine: Engine, novo: gpd.GeoDataFrame, diff: Diff, fonte: str, forcado: bool) -> None:
    """Grava o diff numa transação. Só sobe pro staging as linhas que entram ou mudam."""
    alterar = set(diff.alterados)
    sobe = novo[novo["inscricao"].isin(set(diff.inserir) | alterar)].copy()
    sobe["acao"] = ["alterado" if i in alterar else "novo" for i in sobe["inscricao"]]
    if not sobe.empty:
        sobe.rename_geometry("geom").to_postgis(
            "lotes_sync", engine, schema="staging", if_exists="replace", index=False, chunksize=5000
        )
    alterados: list[int] = []
    inseridos: list[int] = []
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM geo.lotes WHERE inscricao = ANY(CAST(:i AS text[]))"),
                     {"i": diff.apagar})
        if not sobe.empty:
            alterados = conn.execute(text("""
                UPDATE geo.lotes l
                   SET logradouro = s.logradouro, tipo = s.tipo, bairro = s.bairro,
                       geom = ST_Multi(s.geom)
                  FROM staging.lotes_sync s
                 WHERE s.acao = 'alterado' AND l.inscricao = s.inscricao
             RETURNING l.id""")).scalars().all()
            inseridos = conn.execute(text("""
                INSERT INTO geo.lotes (inscricao, setor, quadra, lote, logradouro, tipo, bairro, geom)
                SELECT inscricao, substr(inscricao, 1, 2), substr(inscricao, 3, 3),
                       substr(inscricao, 6, 4), logradouro, tipo, bairro, ST_Multi(geom)
                  FROM staging.lotes_sync WHERE acao = 'novo'
             RETURNING id""")).scalars().all()
            conn.execute(text("DROP TABLE staging.lotes_sync"))
        _recalcular_derivados(conn, list(alterados) + list(inseridos))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS geo.cadastro_sync (
              id bigserial PRIMARY KEY, executado_em timestamptz NOT NULL DEFAULT now(),
              fonte text NOT NULL, lotes integer NOT NULL, novos integer NOT NULL,
              removidos integer NOT NULL, alterados integer NOT NULL, duplicadas integer NOT NULL,
              forcado boolean NOT NULL DEFAULT false)"""))
        conn.execute(
            text("INSERT INTO geo.cadastro_sync (fonte, lotes, novos, removidos, alterados, duplicadas, forcado) "
                 "VALUES (:f, :l, :n, :r, :a, :d, :fo)"),
            {"f": fonte, "l": len(novo), "n": len(diff.novos), "r": len(diff.removidos),
             "a": len(alterados), "d": len(diff.duplicadas), "fo": forcado},
        )
    print(f"aplicado: {len(inseridos)} inseridos, {len(alterados)} atualizados, "
          f"{len(diff.apagar)} inscrições apagadas; zona/altura recalculadas p/ {len(alterados) + len(inseridos)} lotes")


def ler_atual(engine: Engine) -> gpd.GeoDataFrame:
    atual = gpd.read_postgis(
        "SELECT inscricao, logradouro, tipo, bairro, geom FROM geo.lotes",
        engine, geom_col="geom", crs=INTERNAL_SRID,
    )
    return atual.rename_geometry("geometry")


def resumo(diff: Diff, novo: gpd.GeoDataFrame, n_atual: int) -> str:
    d = diff.detalhe
    alt = d[d["acao"] == "alterado"]
    vira = alt[alt["tipo_antes"] != alt["tipo_depois"]]
    mudou = alt["mudou"].fillna("").astype(str)  # sem alterados a coluna vem float (vazia)
    linhas = [
        f"lotes: {n_atual} hoje → {len(novo)} na base nova "
        f"(vagos: {int((novo['tipo'] == 'TERRITORIAL').sum())})",
        f"novos: {len(diff.novos)} | removidos: {len(diff.removidos)} | alterados: {len(diff.alterados)}"
        f" | duplicadas (apaga e reinsere): {len(diff.duplicadas)}",
        f"  vago → construído: {int(((vira['tipo_antes'] == 'TERRITORIAL') & (vira['tipo_depois'] == 'PREDIAL')).sum())}"
        f" | construído → vago: {int(((vira['tipo_antes'] == 'PREDIAL') & (vira['tipo_depois'] == 'TERRITORIAL')).sum())}",
        f"  geometria mudou: {int(mudou.str.contains('geom').sum())}"
        f" | logradouro: {int(mudou.str.contains('logradouro').sum())}"
        f" | bairro: {int(mudou.str.contains('bairro').sum())}",
    ]
    return "\n".join(linhas)


def main() -> None:
    ap = argparse.ArgumentParser(description="Atualiza geo.lotes a partir do cadastro do Filipeia")
    fonte = ap.add_mutually_exclusive_group(required=True)
    fonte.add_argument("--zip", type=Path, help="shapefile de lotes baixado do portal (.zip/.shp)")
    fonte.add_argument("--wfs", action="store_true", help="GeoServer público do Filipeia")
    ap.add_argument("--bairros", type=Path, default=ROOT / "data" / "raw" / "bairros.zip")
    ap.add_argument("--relatorios", type=Path, default=ROOT / "data" / "sync")
    ap.add_argument("--aplicar", action="store_true", help="grava no banco (padrão: só simula)")
    ap.add_argument("--forcar", action="store_true", help="aplica mesmo com as travas disparadas")
    args = ap.parse_args()

    nome_fonte = f"zip:{args.zip.name}" if args.zip else "wfs"
    print(f"lendo {nome_fonte} …")
    novo = normalizar(ler_zip(args.zip) if args.zip else ler_wfs())
    novo = atribuir_bairro(novo, gpd.read_file(args.bairros))

    engine = get_engine()
    atual = ler_atual(engine)
    diff = calcular_diff(atual, novo)
    print(resumo(diff, novo, len(atual)))

    args.relatorios.mkdir(parents=True, exist_ok=True)
    rel = args.relatorios / f"{datetime.now():%Y%m%d_%H%M}_{'zip' if args.zip else 'wfs'}.csv"
    diff.detalhe.to_csv(rel, index=False)
    print(f"relatório: {rel}")

    problemas = validar(len(atual), novo, diff)
    for p in problemas:
        print(f"[TRAVA] {p}")
    if not args.aplicar:
        print("simulação — nada gravado (use --aplicar)")
        return
    if problemas and not args.forcar:
        raise SystemExit("não aplicado: travas disparadas (revise o relatório; --forcar ignora)")
    if not (diff.apagar or diff.inserir or diff.alterados):
        print("nada a aplicar: base igual à atual")
        return
    aplicar(engine, novo, diff, nome_fonte, forcado=bool(problemas))


if __name__ == "__main__":
    main()
