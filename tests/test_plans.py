"""Testes da lógica de planos (pura, sem DB) — limites, default seguro e kill-switch."""
import pytest

from src.api.plans import ENTERPRISE, FREE, PLANS, PRO, limits_for


@pytest.fixture
def gate_on(monkeypatch):
    """Liga o gate (fora da fase demo) para testar os limites reais por tier."""
    monkeypatch.setenv("PLANS_ENFORCED", "1")


def test_demo_libera_tudo_por_padrao(monkeypatch):
    # Sem PLANS_ENFORCED → fase demo: qualquer plano (até None/free) enxerga full.
    monkeypatch.delenv("PLANS_ENFORCED", raising=False)
    assert limits_for(None).codigo == ENTERPRISE
    assert limits_for(FREE).vgv_detalhado is True


def test_default_seguro_para_desconhecido(gate_on):
    # Com gate ligado, plano inválido/None cai em FREE (nunca libera feature paga por engano).
    assert limits_for(None).codigo == FREE
    assert limits_for("inexistente").codigo == FREE


def test_free_nao_tem_features_pagas(gate_on):
    free = limits_for(FREE)
    assert free.vgv_detalhado is False
    assert free.pdf_mes == 0
    assert free.landbank_max == 5


def test_pro_libera_vgv_e_pdf(gate_on):
    pro = limits_for(PRO)
    assert pro.vgv_detalhado is True
    assert pro.pdf_mes and pro.pdf_mes > 0
    assert pro.landbank_max is None  # ilimitado


def test_enterprise_ilimitado_e_api(gate_on):
    ent = limits_for(ENTERPRISE)
    assert ent.api is True
    assert ent.municipios is None and ent.pdf_mes is None and ent.assentos is None


def test_codigos_batem_com_a_chave():
    for codigo, plano in PLANS.items():
        assert plano.codigo == codigo
