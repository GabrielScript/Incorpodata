"""Cenário de financiamento do comprador final (demanda solvável) — funções puras.

Pergunta que responde na ficha: "com os juros de hoje, quem consegue comprar a unidade típica
que sai deste terreno?". A taxa vem do BCB (SGS; ver src/ingest/bcb.py), a unidade típica do
R$/m² de referência do lote (o mesmo do VGV) × área privativa típica.

Premissas explícitas (mercado brasileiro, 2026):
  - entrada 20% (financia até 80% do valor — teto usual dos bancos no SFH/SFI);
  - 30 anos (360 meses), sistema SAC (padrão Caixa) — Price só como comparação;
  - comprometimento de renda de até 30% com a parcela (regra dos bancos);
  - sem seguros MIP/DFI e taxa de administração: parcela real ~5–10% maior (dito na nota).
"""
from __future__ import annotations

from dataclasses import dataclass

ENTRADA_PCT_PADRAO = 0.20
PRAZO_MESES_PADRAO = 360
COMPROMETIMENTO_RENDA = 0.30
AREA_UNIDADE_TIPICA_M2 = 70.0   # 2–3 quartos, padrão de lançamento em JP
SENSIBILIDADE_PP = 1.0          # +1 p.p. na taxa anual


def taxa_mensal(taxa_aa_pct: float) -> float:
    """% a.a. -> taxa mensal equivalente (fração). 14,28% a.a. -> ~0,01119."""
    return (1 + taxa_aa_pct / 100) ** (1 / 12) - 1


def parcela_sac(pv: float, i: float, n: int) -> tuple[float, float]:
    """(1ª parcela, última parcela) no SAC: amortização constante pv/n + juros do saldo."""
    amort = pv / n
    return amort + pv * i, amort + amort * i


def parcela_price(pv: float, i: float, n: int) -> float:
    """Parcela fixa (tabela Price)."""
    if i == 0:
        return pv / n
    return pv * i / (1 - (1 + i) ** -n)


@dataclass(frozen=True)
class Simulacao:
    taxa_aa_pct: float
    valor_imovel: float
    entrada: float
    financiado: float
    prazo_meses: int
    parcela_sac_inicial: float
    parcela_sac_final: float
    parcela_price: float
    renda_minima: float          # 1ª parcela SAC ÷ comprometimento
    renda_minima_mais_1pp: float  # sensibilidade: taxa +1 p.p.


def simular(valor_imovel: float, taxa_aa_pct: float,
            entrada_pct: float = ENTRADA_PCT_PADRAO,
            prazo_meses: int = PRAZO_MESES_PADRAO,
            comprometimento: float = COMPROMETIMENTO_RENDA) -> Simulacao:
    entrada = valor_imovel * entrada_pct
    pv = valor_imovel - entrada
    i = taxa_mensal(taxa_aa_pct)
    ini, fim = parcela_sac(pv, i, prazo_meses)
    ini_1pp, _ = parcela_sac(pv, taxa_mensal(taxa_aa_pct + SENSIBILIDADE_PP), prazo_meses)
    return Simulacao(
        taxa_aa_pct=taxa_aa_pct,
        valor_imovel=valor_imovel,
        entrada=entrada,
        financiado=pv,
        prazo_meses=prazo_meses,
        parcela_sac_inicial=ini,
        parcela_sac_final=fim,
        parcela_price=parcela_price(pv, i, prazo_meses),
        renda_minima=ini / comprometimento,
        renda_minima_mais_1pp=ini_1pp / comprometimento,
    )
