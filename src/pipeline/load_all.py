"""Orquestra a carga completa do TerraIQ, do staging à viabilidade por lote.

Pré-requisitos:
  - PostGIS no ar:  docker compose up -d
  - Arquivos em data/raw/  (Lotes.zip, bairros.zip, zoneamento*.json, r_faixas.json,
    r_centrohist.json, r_barreira.json) e config/luos_parametros.csv

Rodar na raiz do projeto:
    python -m src.pipeline.load_all

Idempotente (pode repetir). Cada passo loga o que fez; um passo que falha não aborta os
demais — o erro aponta o passo, para você ajustar o mapeamento de colunas se um shapefile
tiver nomes diferentes.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from src.db.database import get_engine, init_db
from src.ingest.filipeia import load_layer
from src.zoning.luos import load as load_luos

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
SQLDIR = ROOT / "sql"

# (trecho do nome do arquivo em data/raw, tabela de destino em staging)
LAYERS: list[tuple[str, str]] = [
    ("lotes", "lotes"),
    ("bairros", "bairros"),
    ("zoneamento", "zonas"),
    ("faixas", "faixas"),
    ("centrohist", "centrohist"),
    ("barreira", "barreira"),
]

_EXTS = {".zip", ".json", ".geojson", ".shp"}


def _find(stem: str) -> Path | None:
    """Acha em data/raw/ o arquivo cujo nome contém `stem` (case-insensitive)."""
    if not RAW.exists():
        return None
    for p in sorted(RAW.glob("*")):
        if p.suffix.lower() in _EXTS and stem in p.name.lower():
            return p
    return None


def step(label: str, fn) -> None:
    """Executa um passo, logando ok/erro sem abortar o restante do pipeline."""
    try:
        fn()
        print(f"[ok]   {label}")
    except Exception as exc:  # noqa: BLE001 — queremos seguir e mostrar o passo que falhou
        print(f"[FALHA] {label}: {exc}")


def ingest_all() -> None:
    for stem, table in LAYERS:
        path = _find(stem)
        if path is None:
            print(f"[skip] staging.{table}: nenhum arquivo '*{stem}*' em data/raw/")
            continue
        try:
            load_layer(str(path), table, schema="staging", src_srid=None)
        except SystemExit:
            # .prj/CRS ausente → tenta SIRGAS 2000 geográfico (comum no PB)
            load_layer(str(path), table, schema="staging", src_srid=4674)


def run_sql(name: str) -> None:
    """Roda um script .sql inteiro (psycopg2 cru, p/ múltiplos statements e '%')."""
    sql = (SQLDIR / name).read_text(encoding="utf-8")
    raw = get_engine().raw_connection()
    try:
        cur = raw.cursor()
        cur.execute(sql)
        raw.commit()
    finally:
        raw.close()


def _pick(cols: list[str], candidates: list[str]) -> str | None:
    low = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand in low:
            return low[cand]
    return None


def transform_zonas() -> None:
    """staging.zonas -> geo.zonas, detectando as colunas de sigla/nome (variam por fonte)."""
    eng = get_engine()
    with eng.begin() as conn:
        cols = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='staging' AND table_name='zonas'"
                )
            )
        ]
        if not cols:
            raise RuntimeError("staging.zonas não existe (ingest do zoneamento falhou?)")
        sigla = _pick(cols, ["sigla", "zona", "zoneamento", "cod_zona", "codigo", "cod", "classe", "tipo"])
        nome = _pick(cols, ["nome", "nome_zona", "descricao", "desc", "legenda", "rotulo"])
        if sigla is None:
            raise RuntimeError(f"não achei coluna de sigla em staging.zonas; colunas={cols}")
        nome_sel = f"{nome}::text" if nome else "NULL::text"
        conn.execute(text("TRUNCATE geo.zonas RESTART IDENTITY CASCADE"))
        conn.execute(
            text(
                f"INSERT INTO geo.zonas (sigla, nome, geom) "
                f"SELECT {sigla}::text, {nome_sel}, ST_Multi(ST_Force2D(geom)) FROM staging.zonas"
            )
        )
        print(f"       geo.zonas: sigla='{sigla}', nome='{nome or '(nenhuma)'}'")


def load_luos_csv() -> None:
    csv = ROOT / "config" / "luos_parametros.csv"
    if not csv.exists():
        raise RuntimeError("config/luos_parametros.csv ausente")
    load_luos(str(csv))


def summary() -> None:
    queries = {
        "geo.lotes": "SELECT count(*) FROM geo.lotes",
        "geo.zonas": "SELECT count(*) FROM geo.zonas",
        "geo.lote_zona": "SELECT count(*) FROM geo.lote_zona",
        "geo.lote_restricao": "SELECT count(*) FROM geo.lote_restricao",
        "zoning.parametros": "SELECT count(*) FROM zoning.parametros",
        "lotes em Bancários": "SELECT count(*) FROM geo.lotes WHERE bairro ILIKE 'Bancários'",
    }
    with get_engine().connect() as conn:
        for label, q in queries.items():
            try:
                n: object = conn.execute(text(q)).scalar()
            except Exception as exc:  # noqa: BLE001
                n = f"(erro: {exc})"
            print(f"  {label:24} {n}")


def main() -> None:
    print("== schema ==")
    step("init_db", init_db)
    print("== ingest (data/raw -> staging) ==")
    ingest_all()
    print("== parâmetros LUOS ==")
    step("zoning.parametros", load_luos_csv)
    print("== transforms ==")
    step("transform_filipeia.sql (geo.lotes)", lambda: run_sql("transform_filipeia.sql"))
    step("transform zonas (geo.zonas)", transform_zonas)
    step("buildability.sql (geo.lote_zona)", lambda: run_sql("buildability.sql"))
    step("altura.sql (geo.lote_restricao)", lambda: run_sql("altura.sql"))
    print("== resumo ==")
    summary()
    print("\nPronto. Suba a API (uvicorn src.api.main:app --reload) e o front (cd frontend && npm run dev).")


if __name__ == "__main__":
    main()
