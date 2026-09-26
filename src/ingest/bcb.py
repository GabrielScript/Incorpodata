"""Séries do Banco Central (SGS) -> market.indicadores. API pública, sem chave.

Séries (confirmadas no CKAN do BCB em 2026-09-25):
  20772 — Taxa média de juros, recursos direcionados, PF, financiamento imobiliário com
          taxas de MERCADO (% a.a.)  → SFI / acima do teto do SFH
  20773 — idem, com taxas REGULADAS (% a.a.) → SFH/FGTS (quando o imóvel e a renda se enquadram)

Uso:
    python -m src.ingest.bcb               # últimos 24 meses de cada série
    python -m src.ingest.bcb --meses 120
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import date, datetime

from sqlalchemy import text

SERIES: dict[str, int] = {
    "financ_imob_pf_mercado_aa": 20772,
    "financ_imob_pf_regulada_aa": 20773,
}
# Período por data inicial: o atalho /ultimos/{n} do SGS devolve HTTP 400 para n > 20.
URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{cod}/dados?formato=json&dataInicial={ini}"

_UPSERT = text(
    """
    INSERT INTO market.indicadores (serie, data, valor, fonte)
    VALUES (:serie, :data, :valor, :fonte)
    ON CONFLICT (serie, data) DO UPDATE SET valor = EXCLUDED.valor, carregado_em = now()
    """
)


def parse(payload: list[dict], serie: str, cod: int) -> list[dict]:
    """[{'data': '01/07/2026', 'valor': '14.28'}] -> linhas p/ upsert (datas ISO, valor float)."""
    out = []
    for p in payload:
        try:
            d = datetime.strptime(p["data"], "%d/%m/%Y").date()
            v = float(p["valor"])
        except (KeyError, ValueError, TypeError):
            continue
        out.append({"serie": serie, "data": d, "valor": v, "fonte": f"BCB SGS {cod}"})
    return out


def fetch(cod: int, meses: int) -> list[dict]:
    hoje = date.today()
    ano, mes = divmod(hoje.year * 12 + hoje.month - 1 - meses, 12)
    ini = date(ano, mes + 1, 1).strftime("%d/%m/%Y")
    req = urllib.request.Request(URL.format(cod=cod, ini=ini), headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (URL fixa do BCB)
        return json.loads(r.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="BCB SGS -> market.indicadores")
    ap.add_argument("--meses", type=int, default=24)
    args = ap.parse_args(argv)

    from src.db.database import get_engine

    rows: list[dict] = []
    for serie, cod in SERIES.items():
        got = parse(fetch(cod, args.meses), serie, cod)
        last: date | None = max((r["data"] for r in got), default=None)
        print(f"{serie} ({cod}): {len(got)} meses, último {last} = "
              f"{next((r['valor'] for r in got if r['data'] == last), None)}% a.a.")
        rows.extend(got)
    with get_engine().begin() as conn:
        conn.execute(_UPSERT, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
