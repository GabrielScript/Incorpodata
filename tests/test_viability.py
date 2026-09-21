"""Testes da lógica pura de viabilidade (sem DB)."""
from src.api.viability import (
    APROV_VGV_M2_HIGH,
    APROV_VGV_M2_LOW,
    AREA_LOTE_SUSPEITA_M2,
    CUSTO_OBRA_M2_PADRAO,
    EFICIENCIA_PADRAO,
    LOC_PRECO_M2_HIGH,
    LOC_PRECO_M2_LOW,
    MARGEM_ALVO_PADRAO,
    PAVIMENTOS_PREMISSA_PADRAO,
    SCORE_GAP_FULL,
    SCORE_TERRENO_PCT_FULL,
    PrecoStats,
    altura_label,
    aviso_area_grande,
    escolher_preco_ref,
    estimar_residual,
    estimar_vgv,
    geometria_suspeita,
    incorpo_score,
)

# Lote "no meio de todas as âncoras": cada eixo cai em 0,5 por construção, qualquer que seja a
# calibração. Os testes de transferência verificam a MECÂNICA (linear, centrada), não os números
# das âncoras — que vivem só em viability.py e são revisados contra a distribuição real de JP.
_APROV_MID = (APROV_VGV_M2_LOW + APROV_VGV_M2_HIGH) / 2
_LOC_MID = (LOC_PRECO_M2_LOW + LOC_PRECO_M2_HIGH) / 2
_AREA_LOTE = 1000.0


def _witness(**kw):
    """incorpo_score de um lote no ponto médio das âncoras (cada eixo → 0,5 antes de pesos)."""
    return incorpo_score(
        vgv_por_pavimento=_APROV_MID * _AREA_LOTE,  # aprov_ratio = _APROV_MID → aprov01 = 0,5
        area_lote_m2=_AREA_LOTE,
        preco_m2=_LOC_MID,                          # loc01 = 0,5
        n_comps=30,                                 # n01 = 1,0
        terreno_pct_vgv=0.5 * SCORE_TERRENO_PCT_FULL,
        **kw,
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


# ───────── guarda de plausibilidade: gleba/ZEPA não vira VGV ─────────
def test_geometria_suspeita_pega_gleba():
    assert geometria_suspeita(5_140_263) is True   # maior "lote" real de JP (5,1 km²)
    assert geometria_suspeita(AREA_LOTE_SUSPEITA_M2 + 1) is True


def test_geometria_ok_lote_urbano():
    assert geometria_suspeita(223) is False         # mediana de JP
    assert geometria_suspeita(5_000) is False        # ~p99, ainda lote legítimo
    assert geometria_suspeita(AREA_LOTE_SUSPEITA_M2) is False  # limiar é exclusivo


def test_geometria_suspeita_none():
    assert geometria_suspeita(None) is False         # sem geom → não bloqueia


# ───────── aviso da guarda: ZEPA × gleba (nunca sugere erro de cadastro) ─────────
def test_aviso_none_para_lote_urbano():
    assert aviso_area_grande(223, "ZR1") is None
    assert aviso_area_grande(AREA_LOTE_SUSPEITA_M2, "ZEPA2") is None  # limiar exclusivo
    assert aviso_area_grande(None, None) is None


def test_aviso_zepa1_cita_plano_de_manejo():
    a = aviso_area_grande(1_876_650, "ZEPA1")
    assert "Proteção Ambiental (ZEPA1)" in a
    assert "187,7 ha" in a
    assert "plano de manejo" in a


def test_aviso_zepa2_cita_licenciamento():
    a = aviso_area_grande(423_314, "ZEPA-2")  # sigla com hífen (CSV da LUOS) também casa
    assert "(ZEPA2)" in a
    assert "licenciamento ambiental" in a
    assert "plano de manejo" not in a


def test_aviso_gleba_fora_de_zepa():
    a = aviso_area_grande(50_000, "ZH2")
    assert a.startswith("Gleba de 5,0 ha")
    assert "parcelamento" in a
    assert aviso_area_grande(50_000, None).startswith("Gleba")  # sem zona → gleba


def test_aviso_nunca_sugere_erro_de_cadastro():
    for sigla in ("ZEPA1", "ZEPA2", "ZH2", None):
        a = aviso_area_grande(100_000, sigla)
        assert "erro de cadastro" not in a
        assert "VGV" in a


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


# ───────── valor residual (involutivo): "quanto pagar" pelo terreno ─────────
# fator_vgv = 1 − custos(0,16) − margem(0,20) = 0,64.  residual = VGV×0,64 − obra.
def test_residual_basico():
    # projeção 300 × efic 0,8 = 240 m²/pavto × R$6.000 = VGV/pavto 1,44 mi (1 pav → total = pavto)
    v = estimar_vgv(300, 6000, pavimentos=1, eficiencia=0.8)
    r = estimar_residual(
        v, custo_obra_m2=2000, margem_alvo=0.20,
        impostos_pct=0.06, comercializacao_pct=0.05, indiretos_pct=0.05,
    )
    # 1.440.000 × 0,64 − (300 × 2000) = 921.600 − 600.000 = 321.600
    assert round(r.residual_por_pavimento, 2) == 321_600.0
    assert round(r.residual_total, 2) == 321_600.0
    assert round(r.terreno_pct_vgv, 4) == 0.2233   # 321.600 / 1.440.000


def test_residual_escala_com_pavimentos():
    v = estimar_vgv(300, 6000, pavimentos=8, eficiencia=0.8)
    r = estimar_residual(v, custo_obra_m2=2000, margem_alvo=0.20,
                         impostos_pct=0.06, comercializacao_pct=0.05, indiretos_pct=0.05)
    # VGV total 11,52 mi × 0,64 − (2400 m² constr × 2000) = 7.372.800 − 4.800.000 = 2.572.800
    assert round(r.residual_por_pavimento, 2) == 321_600.0
    assert round(r.residual_total, 2) == 2_572_800.0


def test_residual_faixa_q1_q3_propaga():
    # custo de obra é FIXO (não depende do preço de venda) → só o VGV varia com Q1/Q3
    v = estimar_vgv(300, 6000, pavimentos=1, eficiencia=0.8, preco_m2_q1=5000, preco_m2_q3=7500)
    r = estimar_residual(v, custo_obra_m2=2000, margem_alvo=0.20,
                         impostos_pct=0.06, comercializacao_pct=0.05, indiretos_pct=0.05)
    assert round(r.residual_por_pavimento_min, 2) == 168_000.0   # 1.200.000 × 0,64 − 600.000
    assert round(r.residual_por_pavimento_max, 2) == 552_000.0   # 1.800.000 × 0,64 − 600.000
    assert round(r.residual_total_min, 2) == 168_000.0
    assert round(r.residual_total_max, 2) == 552_000.0


def test_residual_sem_quartis_faixa_none():
    v = estimar_vgv(300, 6000, pavimentos=1, eficiencia=0.8)
    r = estimar_residual(v, custo_obra_m2=2000)
    assert r.residual_por_pavimento_min is None
    assert r.residual_por_pavimento_max is None
    assert r.residual_total_min is None
    assert r.residual_total_max is None


def test_residual_negativo_quando_obra_alta():
    # obra cara demais p/ a margem-alvo → residual negativo (lote inviável às premissas)
    v = estimar_vgv(300, 6000, pavimentos=1, eficiencia=0.8)
    r = estimar_residual(v, custo_obra_m2=5000, margem_alvo=0.20,
                         impostos_pct=0.06, comercializacao_pct=0.05, indiretos_pct=0.05)
    # 921.600 − (300 × 5000 = 1.500.000) = −578.400
    assert round(r.residual_total, 2) == -578_400.0
    assert r.terreno_pct_vgv < 0


def test_residual_gap_cabe_no_bolso():
    v = estimar_vgv(300, 6000, pavimentos=1, eficiencia=0.8)   # residual_total = 321.600
    r = estimar_residual(v, custo_obra_m2=2000, margem_alvo=0.20,
                         impostos_pct=0.06, comercializacao_pct=0.05, indiretos_pct=0.05,
                         preco_pedido=250_000)
    # gap = (321.600 − 250.000) / 321.600 = 0,2226 ; pedido abaixo do máximo → cabe
    assert round(r.gap_pct, 4) == 0.2226
    assert r.cabe_no_bolso is True


def test_residual_gap_caro_demais():
    v = estimar_vgv(300, 6000, pavimentos=1, eficiencia=0.8)   # residual_total = 321.600
    r = estimar_residual(v, custo_obra_m2=2000, margem_alvo=0.20,
                         impostos_pct=0.06, comercializacao_pct=0.05, indiretos_pct=0.05,
                         preco_pedido=400_000)
    assert r.gap_pct < 0
    assert r.cabe_no_bolso is False


def test_residual_gap_none_sem_preco():
    v = estimar_vgv(300, 6000, pavimentos=1, eficiencia=0.8)
    r = estimar_residual(v, custo_obra_m2=2000)
    assert r.gap_pct is None
    assert r.cabe_no_bolso is None


def test_residual_gap_none_quando_residual_negativo():
    # sem residual positivo não há "barganha" a calcular (divisão sem sentido)
    v = estimar_vgv(300, 6000, pavimentos=1, eficiencia=0.8)
    r = estimar_residual(v, custo_obra_m2=5000, preco_pedido=100_000)
    assert r.gap_pct is None
    assert r.cabe_no_bolso is None


def test_residual_usa_defaults():
    v = estimar_vgv(300, 6000, pavimentos=1, eficiencia=0.8)
    r = estimar_residual(v)
    assert r.custo_obra_m2 == CUSTO_OBRA_M2_PADRAO
    assert r.margem_alvo == MARGEM_ALVO_PADRAO
    assert round(r.custos_indiretos_pct, 2) == 0.16   # 0,06 + 0,05 + 0,05


# ───────── IncorpoScore (ranking 0–100 + decomposição em 4 eixos) ─────────
def test_score_rentabilidade_com_gap():
    # gap = saturação cheia → rent01 = clamp(0,5 + 1,0) = 1,0 → nota 10 (independe da calibração)
    sb = _witness(gap_pct=SCORE_GAP_FULL)
    assert sb.rentabilidade == 10.0


def test_score_rentabilidade_sem_anuncio_usa_terreno_pct():
    # sem gap (sem anúncio) → usa terreno/VGV; no ponto médio (0,5·FULL) → 0,5 → nota 5
    sb = _witness(gap_pct=None)
    assert sb.rentabilidade == 5.0


def test_score_rentabilidade_clamp():
    alto = _witness(gap_pct=1.0)        # 0,5 + 1,0/0,40 → clamp 1,0
    baixo = _witness(gap_pct=-0.30)     # 0,5 − 0,75 → clamp 0
    assert alto.rentabilidade == 10.0
    assert baixo.rentabilidade == 0.0


def test_score_aproveitamento():
    # VGV/pavto por m² de terreno no ponto médio das âncoras → nota 5 (transferência centrada)
    sb = _witness(gap_pct=0.0)
    assert sb.aproveitamento == 5.0


def test_score_localizacao():
    # preço/m² no ponto médio das âncoras → nota 5 (transferência centrada)
    sb = _witness(gap_pct=0.0)
    assert sb.localizacao == 5.0


def test_score_confianca_n_e_iqr():
    # n=30 → n01=1,0 ; IQR rel = (9000−6000)/7500 = 0,4 → iqr01 = 1 − 0,4/0,6 = 0,3333
    # confiança = (1,0 + 0,3333)/2 = 0,6667 → nota 6,67
    sb = incorpo_score(2_500_000, 1000, 7500, 30, terreno_pct_vgv=0.15, gap_pct=0.0,
                       q1=6000, q3=9000)
    assert round(sb.confianca, 2) == 6.67


def test_score_confianca_sem_quartis_neutro():
    # sem Q1/Q3 a dispersão é neutra (0,5); n=5 → n01=0,3 → conf=(0,3+0,5)/2=0,4 → nota 4
    sb = incorpo_score(2_500_000, 1000, 7500, 5, terreno_pct_vgv=0.15, gap_pct=0.0)
    assert sb.confianca == 4.0


def test_score_total_pondera_eixos():
    # rent .5, aprov .5, loc .5, conf .75 → 0,35·.5+0,25·.5+0,25·.5+0,15·.75 = 0,5375 → 53,75
    sb = _witness(gap_pct=0.0)
    assert abs(sb.total - 53.75) < 0.01
    assert sb.penalidade_altura is False


def test_score_penalidade_altura_restrita():
    base = _witness(gap_pct=0.0)
    pen = _witness(gap_pct=0.0, em_centro_historico=True)
    assert pen.penalidade_altura is True
    assert abs(pen.total - base.total * 0.70) < 0.01
