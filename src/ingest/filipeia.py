"""Ingest das camadas do Filipeia (geoportal oficial da PMJP) para PostGIS.

⚠️ Download é MANUAL pelo navegador. O portal de download
(https://filipeia.joaopessoa.pb.gov.br/files/donwload/) fica atrás de WAF (Incapsula)
e bloqueia robôs. Isso é carga periódica (não scrape recorrente), então:

  1. Abra o Filipeia e baixe os shapefiles (.zip) das camadas:
     Lotes, Quadras, Bairros, Logradouros, Zoneamento.
  2. Coloque os .zip em data/raw/.
  3. Carregue em tabelas de STAGING (passthrough — preserva os atributos originais):

       python -m src.ingest.filipeia --path data/raw/lotes.zip       --table lotes
       python -m src.ingest.filipeia --path data/raw/zoneamento.zip  --table zonas
       python -m src.ingest.filipeia --path data/raw/bairros.zip     --table bairros

  4. Depois inspecione as colunas (cada shapefile tem nomes próprios) e mapeie
     staging.* → geo.lotes / geo.zonas em sql/transform_filipeia.sql.

Se o .prj vier ausente, informe o SRID de origem com --src-srid (Filipeia costuma ser
SIRGAS 2000 / UTM 25S = 31985, ou geográfico 4674).
"""
from __future__ import annotations

import argparse

import geopandas as gpd

from src.db.database import INTERNAL_SRID, get_engine


def load_layer(
    path: str,
    table: str,
    schema: str = "staging",
    src_srid: int | None = None,
    target_srid: int = INTERNAL_SRID,
    if_exists: str = "replace",
) -> int:
    gdf = gpd.read_file(path)  # aceita .zip de shapefile diretamente

    if gdf.crs is None:
        if src_srid is None:
            raise SystemExit(
                f"{path}: sem CRS (.prj ausente). Reexecute com --src-srid (ex.: 31985)."
            )
        gdf = gdf.set_crs(epsg=src_srid)

    gdf = gdf.to_crs(epsg=target_srid)
    gdf.columns = [c.lower() for c in gdf.columns]
    gdf = gdf.rename_geometry("geom")

    engine = get_engine()
    gdf.to_postgis(table, engine, schema=schema, if_exists=if_exists, index=False, chunksize=10000)
    print(f"{len(gdf)} feições -> {schema}.{table} (SRID {target_srid})")
    print("colunas:", ", ".join(c for c in gdf.columns if c != "geom"))
    return len(gdf)


def main() -> None:
    ap = argparse.ArgumentParser(description="Carrega camada do Filipeia (shapefile) no PostGIS")
    ap.add_argument("--path", required=True, help="caminho do .zip/.shp em data/raw/")
    ap.add_argument("--table", required=True, help="nome da tabela de destino")
    ap.add_argument("--schema", default="staging")
    ap.add_argument("--src-srid", type=int, default=None, help="SRID de origem se .prj ausente")
    args = ap.parse_args()
    load_layer(args.path, args.table, args.schema, args.src_srid)


if __name__ == "__main__":
    main()
