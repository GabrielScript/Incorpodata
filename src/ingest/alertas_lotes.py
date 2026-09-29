"""Alertas por lote vago (geo.lote_alerta) a partir de camadas do próprio Filipeia.

"Vago" no cadastro é TIPO_IMOVE = TERRITORIAL — dado de IPTU, que atrasa. Cruzamos cada
lote vago com três camadas do GeoServer público da prefeitura:
  EDIFICACOES  → % da área sob edificação mapeada e nº de edificações (ponto interno no lote)
  MassasDagua  → % da área dentro de rio/lagoa/área alagada
  Rios         → se algum eixo de rio atravessa o lote
A regra de quando isso vira alerta (limiares) vive em src/api/viability.py; aqui só medimos.

Refaz a tabela inteira numa transação. Rodar depois de cada `sync_lotes --aplicar`:

    python -m src.ingest.alertas_lotes            # baixa as camadas do WFS e grava
    python -m src.ingest.alertas_lotes --simular  # só mostra a distribuição
"""
from __future__ import annotations

import argparse

import geopandas as gpd
import pandas as pd
import shapely
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.api.viability import ALERTA_AGUA_PCT, ALERTA_EDIFICADO_PCT, tem_alerta
from src.db.database import INTERNAL_SRID, get_engine
from src.ingest.filipeia_wfs import baixar_camada

# Footprint menor que isso é ruído de desenho (poste, caixa d'água, lasca de vizinho).
EDIFICACAO_MIN_M2 = 20.0

_DDL = """
CREATE TABLE IF NOT EXISTS geo.lote_alerta (
  lote_id        bigint PRIMARY KEY REFERENCES geo.lotes(id) ON DELETE CASCADE,
  pct_edificado  numeric NOT NULL,
  n_edificacoes  integer NOT NULL,
  pct_agua       numeric NOT NULL,
  corta_rio      boolean NOT NULL,
  calculado_em   timestamptz NOT NULL DEFAULT now()
)"""


def _validas(g: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    g = g[g.geometry.notna() & ~g.geometry.is_empty].copy()
    g["geometry"] = shapely.make_valid(shapely.force_2d(g.geometry.to_numpy()))
    return g


def _area_coberta(lotes: gpd.GeoDataFrame, camada: gpd.GeoDataFrame) -> pd.Series:
    """Área (m²) de cada lote coberta pela camada, somada par a par via índice espacial.

    Sem dissolver a camada: rápido p/ ~290 mil edificações. Onde a camada se sobrepõe a si
    mesma a soma conta em dobro — por isso quem usa limita a 100% da área do lote.
    """
    pares = gpd.sjoin(camada[["geometry"]], lotes[["geometry"]], predicate="intersects")
    if pares.empty:
        return pd.Series(0.0, index=lotes.index)
    inter = shapely.intersection(pares.geometry.to_numpy(), lotes.geometry.loc[pares["index_right"]].to_numpy())
    return pd.Series(shapely.area(inter), index=pares["index_right"].to_numpy()).groupby(level=0).sum()


def calcular_alertas(
    vagos: gpd.GeoDataFrame,
    edificacoes: gpd.GeoDataFrame,
    agua: gpd.GeoDataFrame,
    rios: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Uma linha por lote vago: lote_id, pct_edificado, n_edificacoes, pct_agua, corta_rio.

    `vagos` precisa da coluna `id`; todas as camadas no mesmo CRS métrico.
    """
    lotes = _validas(vagos[["id", "geometry"]]).reset_index(drop=True)
    area = lotes.area

    edif = _validas(edificacoes[["geometry"]])
    edif = edif[edif.area >= EDIFICACAO_MIN_M2]
    pct_edif = (_area_coberta(lotes, edif).reindex(lotes.index, fill_value=0.0) / area * 100).clip(upper=100)
    pts = gpd.GeoDataFrame(geometry=edif.representative_point(), crs=edif.crs)
    n_edif = gpd.sjoin(pts, lotes[["geometry"]], predicate="within").groupby("index_right").size()

    # Massas d'água se sobrepõem (lagoa dentro de área alagada): dissolve antes de medir.
    agua_u = gpd.GeoDataFrame(geometry=[_validas(agua[["geometry"]]).union_all()], crs=agua.crs)
    pct_agua = (_area_coberta(lotes, agua_u).reindex(lotes.index, fill_value=0.0) / area * 100).clip(upper=100)

    rio = gpd.sjoin(lotes[["geometry"]], _validas(rios[["geometry"]]), predicate="intersects").index.unique()

    return pd.DataFrame({
        "lote_id": lotes["id"].astype(int),
        "pct_edificado": pct_edif.round(1),
        "n_edificacoes": n_edif.reindex(lotes.index, fill_value=0).astype(int),
        "pct_agua": pct_agua.round(1),
        "corta_rio": lotes.index.isin(rio),
    })


def gravar(engine: Engine, alertas: pd.DataFrame) -> None:
    with engine.begin() as conn:
        conn.execute(text(_DDL))
        conn.execute(text("DELETE FROM geo.lote_alerta"))
        conn.execute(
            text("INSERT INTO geo.lote_alerta (lote_id, pct_edificado, n_edificacoes, pct_agua, corta_rio) "
                 "VALUES (:lote_id, :pct_edificado, :n_edificacoes, :pct_agua, :corta_rio)"),
            alertas.to_dict("records"),
        )


def main() -> None:
    ap =argparse.ArgumentParser(description="Recalcula geo.lote_alerta (vagos × camadas do Filipeia)")
    ap.add_argument("--simular", action="store_true", help="só mostra a distribuição, não grava")
    args = ap.parse_args()

    engine = get_engine()
    vagos = gpd.read_postgis(
        "SELECT id, geom FROM geo.lotes WHERE tipo = 'TERRITORIAL'", engine, geom_col="geom", crs=INTERNAL_SRID
    ).rename_geometry("geometry")
    print(f"{len(vagos)} lotes vagos; baixando camadas do Filipeia …")
    edif = baixar_camada("EDIFICACOES", ["N_PAVIM"])
    agua = baixar_camada("MassasDagua", ["nm_generic"])
    rios = baixar_camada("Rios", ["Nome"])
    print(f"  {len(edif)} edificações, {len(agua)} massas d'água, {len(rios)} rios")

    al = calcular_alertas(vagos, edif, agua, rios)
    alerta = [tem_alerta(e, a, r) for e, a, r in zip(al["pct_edificado"], al["pct_agua"], al["corta_rio"])]
    print(f"com edificação >{ALERTA_EDIFICADO_PCT:.0f}%: {int((al['pct_edificado'] > ALERTA_EDIFICADO_PCT).sum())}"
          f" | água >{ALERTA_AGUA_PCT:.0f}%: {int((al['pct_agua'] > ALERTA_AGUA_PCT).sum())}"
          f" | cortados por rio: {int(al['corta_rio'].sum())}"
          f" | com algum alerta: {sum(alerta)} de {len(al)}")
    if args.simular:
        print("simulação — nada gravado")
        return
    gravar(engine, al)
    print(f"geo.lote_alerta: {len(al)} linhas gravadas")


if __name__ == "__main__":
    main()
