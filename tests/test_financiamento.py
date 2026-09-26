"""Cenário de financiamento (SAC/Price) e parsing do SGS do BCB — sem rede/DB."""
import math

from src.api.financiamento import parcela_price, parcela_sac, simular, taxa_mensal
from src.ingest.bcb import parse


def test_taxa_mensal_equivalente():
    # 12,6825% a.a. ≡ 1% a.m. (1,01^12)
    assert math.isclose(taxa_mensal(12.6825), 0.01, rel_tol=1e-4)


def test_sac_conta_de_cabeca():
    # 360 mil a 1% a.m. em 360x: amortização 1.000; 1ª = 1.000 + 3.600; última = 1.000 + 10
    ini, fim = parcela_sac(360_000, 0.01, 360)
    assert math.isclose(ini, 4_600) and math.isclose(fim, 1_010)


def test_price_formula_classica():
    # 100 mil, 1% a.m., 12x → 8.884,88 (tabela Price de livro)
    assert math.isclose(parcela_price(100_000, 0.01, 12), 8_884.88, abs_tol=0.01)


def test_simular_renda_minima_e_sensibilidade():
    s = simular(500_000, taxa_aa_pct=14.28)
    assert s.entrada == 100_000 and s.financiado == 400_000
    assert math.isclose(s.renda_minima, s.parcela_sac_inicial / 0.30)
    assert s.renda_minima_mais_1pp > s.renda_minima            # juro sobe → renda exigida sobe
    assert s.parcela_sac_inicial > s.parcela_price > s.parcela_sac_final


def test_parse_sgs():
    rows = parse([{"data": "01/07/2026", "valor": "14.28"}, {"data": "x", "valor": "?"}],
                 "financ_imob_pf_mercado_aa", 20772)
    assert len(rows) == 1
    assert rows[0]["valor"] == 14.28 and rows[0]["data"].isoformat() == "2026-07-01"
    assert rows[0]["fonte"] == "BCB SGS 20772"
