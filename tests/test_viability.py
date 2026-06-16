"""Testes da lógica pura de viabilidade (sem DB)."""
from src.api.viability import altura_label


def test_altura_livre():
    assert altura_label(None, False, False, True) == "Livre — limitada pelos recuos"


def test_iphaep():
    assert "IPHAEP" in altura_label(None, True, False, False)


def test_barreira():
    assert "barreira" in altura_label(None, False, True, False).lower()


def test_faixa_orla():
    assert "orla" in altura_label("3ª", False, False, False).lower()


def test_iphaep_mais_restritivo_que_orla():
    # lote na faixa da orla E no centro histórico → IPHAEP manda
    assert "IPHAEP" in altura_label("1ª", True, False, False)


def test_indefinido():
    assert altura_label(None, False, False, None) == "A confirmar"
