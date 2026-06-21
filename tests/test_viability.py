"""Testes da lógica pura de viabilidade (sem DB)."""
from src.api.viability import (
    EFICIENCIA_PADRAO,
    PAVIMENTOS_PREMISSA_PADRAO,
    PrecoStats,
    altura_label,
    escolher_preco_ref,
    estimar_vgv,
)


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


# ───────── VGV (envelope LUOS × R$/m² do bairro) ─────────
def test_vgv_por_pavimento():
    # projeção 300 m² × eficiência 0,8 = 240 m² privativos/pavto × R$ 6.000 = R$ 1,44 mi
    v = estimar_vgv(300, 6000, pavimentos=1, eficiencia=0.8)
    assert v is not None
    assert v.area_privativa_pavto_m2 == 240.0
    assert v.vgv_por_pavimento == 1_440_000.0
    assert v.vgv_total == 1_440_000.0


def test_vgv_escala_com_pavimentos():
    v = estimar_vgv(300, 6000, pavimentos=8, eficiencia=0.8)
    assert v.area_construida_m2 == 2400.0
    assert v.area_privativa_total_m2 == 1920.0
    assert v.vgv_total == 11_520_000.0


def test_vgv_usa_defaults():
    v = estimar_vgv(300, 6000)  # pavimentos=4, eficiência=0,8
    assert v.pavimentos == PAVIMENTOS_PREMISSA_PADRAO == 4
    assert v.eficiencia == EFICIENCIA_PADRAO == 0.8
    assert v.vgv_total == 5_760_000.0  # 300×0,8×6000×4


def test_vgv_none_sem_projecao():
    assert estimar_vgv(None, 6000) is None
    assert estimar_vgv(0, 6000) is None


def test_vgv_none_sem_preco():
    assert estimar_vgv(300, None) is None
    assert estimar_vgv(300, 0) is None


def test_vgv_none_pavimentos_invalido():
    assert estimar_vgv(300, 6000, pavimentos=0) is None


def test_vgv_margem_com_custos():
    v = estimar_vgv(300, 6000, pavimentos=8, custo_obra_m2=2500, custo_terreno=1_000_000)
    assert v.custo_obra == 6_000_000.0          # 2400 m² construídos × 2500
    assert v.margem == 4_520_000.0              # 11,52 mi − 6 mi − 1 mi
    assert round(v.margem_pct, 4) == 0.3924


def test_vgv_margem_none_sem_custo_obra():
    # sem custo de obra não dá pra falar de margem (obra é o custo dominante)
    v = estimar_vgv(300, 6000, pavimentos=8, custo_terreno=1_000_000)
    assert v.custo_obra is None
    assert v.margem is None
    assert v.margem_pct is None


# ───────── VGV em FAIXA (Q1–Q3, contra a falsa precisão da mediana) ─────────
def test_vgv_faixa_com_quartis():
    # q1=5000, mediana=6000, q3=7500; projeção 300 × efic 0,8 = 240 m² privativos/pavto
    v = estimar_vgv(300, 6000, pavimentos=1, eficiencia=0.8, preco_m2_q1=5000, preco_m2_q3=7500)
    assert v.vgv_por_pavimento == 1_440_000.0       # mediana
    assert v.vgv_por_pavimento_min == 1_200_000.0   # 240 × 5000
    assert v.vgv_por_pavimento_max == 1_800_000.0   # 240 × 7500
    assert v.vgv_total_min == 1_200_000.0
    assert v.vgv_total_max == 1_800_000.0


def test_vgv_faixa_escala_com_pavimentos():
    v = estimar_vgv(300, 6000, pavimentos=8, eficiencia=0.8, preco_m2_q1=5000, preco_m2_q3=7500)
    assert v.vgv_total_min == 9_600_000.0    # 240 × 5000 × 8
    assert v.vgv_total_max == 14_400_000.0   # 240 × 7500 × 8


def test_vgv_sem_quartis_faixa_none():
    # sem Q1/Q3 a faixa não existe (back-compat com a chamada antiga)
    v = estimar_vgv(300, 6000)
    assert v.vgv_por_pavimento_min is None
    assert v.vgv_por_pavimento_max is None
    assert v.vgv_total_min is None
    assert v.vgv_total_max is None


# ───────── escolha do preço de referência: raio do lote × fallback bairro ─────────
def test_preco_ref_usa_raio_quando_n_suficiente():
    raio = PrecoStats(preco_m2=6000, q1=5000, q3=7500, n=12)
    bairro = PrecoStats(preco_m2=5000, q1=4000, q3=6000, n=300)
    ref = escolher_preco_ref(raio, bairro, n_min=5)
    assert ref.fonte == "raio"
    assert ref.preco_m2 == 6000
    assert ref.n == 12


def test_preco_ref_cai_no_bairro_quando_raio_ralo():
    raio = PrecoStats(preco_m2=6000, q1=5000, q3=7500, n=3)
    bairro = PrecoStats(preco_m2=5000, q1=4000, q3=6000, n=300)
    ref = escolher_preco_ref(raio, bairro, n_min=5)
    assert ref.fonte == "bairro"
    assert ref.preco_m2 == 5000
    assert ref.n == 300


def test_preco_ref_bairro_quando_sem_raio():
    bairro = PrecoStats(preco_m2=5000, q1=4000, q3=6000, n=300)
    ref = escolher_preco_ref(None, bairro, n_min=5)
    assert ref.fonte == "bairro"
    assert ref.preco_m2 == 5000


def test_preco_ref_none_quando_sem_dados():
    assert escolher_preco_ref(None, None) is None
    # raio ralo e sem bairro → nada confiável
    assert escolher_preco_ref(PrecoStats(6000, 5000, 7500, 2), None, n_min=5) is None
