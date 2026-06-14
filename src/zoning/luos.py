"""Carrega parâmetros urbanísticos da LUOS (LC 166/2024) em zoning.parametros.

Preencha config/luos_parametros.csv com os valores dos anexos da LC 166/2024
(https://planodiretor.joaopessoa.pb.gov.br/). Veja config/luos_parametros.exemplo.csv
para o formato. Depois:

    python -m src.zoning.luos --csv config/luos_parametros.csv
"""
from __future__ import annotations

import argparse
import csv

from sqlalchemy import text

from src.db.database import get_engine

COLS = [
    "sigla", "nome", "to_max_pct", "tap_min_pct", "recuo_frontal_m",
    "recuo_lateral", "recuo_fundo", "ia_max", "gabarito_obs", "usos_obs",
    "notas",
]

_INSERT = text(
    f"INSERT INTO zoning.parametros ({','.join(COLS)}) "
    f"VALUES ({','.join(':' + c for c in COLS)}) "
    f"ON CONFLICT (sigla) DO UPDATE SET "
    + ", ".join(f"{c}=EXCLUDED.{c}" for c in COLS if c != "sigla")
)


def load(csv_path: str) -> int:
    with open(csv_path, encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("sigla")]
    engine = get_engine()
    with engine.begin() as conn:
        for r in rows:
            conn.execute(_INSERT, {c: (r.get(c) or None) for c in COLS})
    print(f"{len(rows)} zonas -> zoning.parametros")
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="Carrega parâmetros LUOS no PostGIS")
    ap.add_argument("--csv", default="config/luos_parametros.csv")
    args = ap.parse_args()
    load(args.csv)


if __name__ == "__main__":
    main()
