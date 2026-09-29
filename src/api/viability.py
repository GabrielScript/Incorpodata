"""Lógica pura da ficha de viabilidade (sem DB) — o moat, por isso testada.

Em João Pessoa a altura/nº de pavimentos é ESPACIAL (faixa de 500m da orla + IPHAEP +
barreira do Cabo Branco), não vem da zona. Aqui traduzimos as flags por lote
(geo.lote_restricao) num rótulo legível. Ordem = mais restritivo primeiro.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Premissas do estudo de massa (o incorporador ajusta; aqui são defaults transparentes).
EFICIENCIA_PADRAO = 0.80          # área privativa ÷ área construída (desconta circulação/comum)
PAVIMENTOS_PREMISSA_PADRAO = 4    # altura em JP é ESPACIAL; sem a camada carregada, premissa baixa

# Premissas do involutivo (valor residual = "quanto pagar"). O incorporador ajusta; defaults
# transparentes p/ ranquear lotes em massa. Custos abaixo são % do VGV (receita).
MARGEM_ALVO_PADRAO = 0.20          # lucro mínimo sobre VGV que o terreno precisa deixar
IMPOSTOS_PCT_PADRAO = 0.06         # RET incorporação afetada (~4%) + extras
COMERCIALIZACAO_PCT_PADRAO = 0.05  # corretagem + marketing
INDIRETOS_PCT_PADRAO = 0.05        # projetos, legalização, incorporação, admin de obra
# Custo de obra p/ ranquear lotes SEM custo informado. Base: CUB-PB R-8 Padrão Normal =
# R$ 1.692,01/m² (tabela oficial Sinduscon-JP, NBR 12.721:2006, maio/2026). A própria nota da
# tabela diz que o CUB NÃO inclui: fundação, elevador, instalações (ar-cond...), projetos,
# remuneração do construtor nem do incorporador. Uplift ~1,6× (BDI/construtor + elevador +
# fundação + projetos) ≈ R$ 2.700/m². Premissa MAIS sensível do residual → sempre exibida na
# ficha; o incorporador calibra ao seu caderno de obra. Sanity: terreno/VGV ~15-20% em lote médio.
CUSTO_OBRA_M2_PADRAO = 2700.0      # R$/m² de área construída (médio padrão verticalizado JP)

# Guarda de plausibilidade: acima disto o "lote" é gleba/ZEPA/área institucional, não lote
# urbano edificável. Distribuição real de João Pessoa (186 mil lotes): mediana ~223 m², p99
# ~5.000 m², max 5,14 milhões m². 30.000 m² isola a cauda (~0,17% dos lotes) sem pegar lote
# grande legítimo. VGV nesses é suprimido — área × TO% × R$/m² numa gleba de hectares cospe
# bilhões sem sentido de incorporação. Conferido no Neon em 21/09/2026: dos 322 acima do limiar,
# nenhum polígono contém outros lotes (não é quadra desenhada como lote) e ~40% dos vagos são
# ZEPA — é gleba real, não erro de cadastro; por isso o aviso não manda "conferir geometria".
AREA_LOTE_SUSPEITA_M2 = 30000.0


def geometria_suspeita(area_geom_m2: float | None) -> bool:
    """True se a área do lote é grande demais p/ ser lote urbano edificável (gleba/ZEPA)."""
    return area_geom_m2 is not None and area_geom_m2 > AREA_LOTE_SUSPEITA_M2


def aviso_area_grande(area_geom_m2: float | None, sigla: str | None) -> str | None:
    """Por que o VGV foi suprimido, em linguagem de incorporador; None se a guarda não dispara.

    ZEPA segue a LUOS (config/luos_parametros.csv): ZEPA-1 = uso conforme plano de manejo,
    sem TO; ZEPA-2/3 = TO 40% com licenciamento ambiental. Fora de ZEPA é gleba: precisa de
    parcelamento (Lei 6.766/79) antes de incorporar. O % de doação de áreas públicas vem da lei
    municipal desde a Lei 9.785/99 — por isso não citamos número.
    """
    if area_geom_m2 is None or not geometria_suspeita(area_geom_m2):
        return None
    ha = f"{area_geom_m2 / 10_000:.1f}".replace(".", ",")
    zona = re.sub(r"[^A-Z0-9]", "", (sigla or "").upper())
    if zona.startswith("ZEPA"):
        regra = (
            "uso conforme plano de manejo"
            if zona == "ZEPA1"
            else "ocupação sujeita a licenciamento ambiental"
        )
        return (
            f"Zona Especial de Proteção Ambiental ({zona}), {ha} ha — {regra}. "
            "VGV de prédio único não se aplica."
        )
    return (
        f"Gleba de {ha} ha — precisa de parcelamento do solo (Lei 6.766/79 e lei municipal) "
        "antes de incorporar, e parte da área vira vias e áreas públicas. "
        "VGV de prédio único não se aplica."
    )


# Alertas de "vago que talvez não seja vago/edificável" (geo.lote_alerta, calculado por
# src/ingest/alertas_lotes.py contra camadas do próprio Filipeia). Auditoria de 28/09/2026:
# 2.279 dos 23.682 vagos têm >25% da área sob edificação mapeada (o IPTU diz TERRITORIAL);
# 41 têm >25% dentro de rio/lagoa (loteamento no papel sobre água). Abaixo de 25% é, na maior
# parte, desalinhamento de desenho com o vizinho — não alerta.
ALERTA_EDIFICADO_PCT = 25.0
ALERTA_AGUA_PCT = 25.0


def tem_alerta(pct_edificado: float | None, pct_agua: float | None, corta_rio: bool | None) -> bool:
    """True se o lote vago tem sinal de construção, de água ou de rio atravessando."""
    return (
        (pct_edificado or 0.0) > ALERTA_EDIFICADO_PCT
        or (pct_agua or 0.0) > ALERTA_AGUA_PCT
        or bool(corta_rio)
    )


def avisos_alerta(
    pct_edificado: float | None,
    n_edificacoes: int | None,
    pct_agua: float | None,
    corta_rio: bool | None,
) -> list[str]:
    """Avisos da ficha, em linguagem de incorporador. Vazio se nada dispara."""
    avisos: list[str] = []
    if (pct_edificado or 0.0) > ALERTA_EDIFICADO_PCT:
        n = n_edificacoes or 0
        qtd = f" ({n} edificaç{'ão' if n == 1 else 'ões'})" if n else ""
        avisos.append(
            f"Possível construção: {pct_edificado:.0f}% da área aparece coberta por edificações "
            f"no mapeamento da prefeitura{qtd}, embora o cadastro diga vago. "
            "Confira no satélite ou no Street View antes de seguir."
        )
    if (pct_agua or 0.0) > ALERTA_AGUA_PCT:
        avisos.append(
            f"{pct_agua:.0f}% do lote fica dentro de rio, lagoa ou área alagada mapeada pela "
            "prefeitura — essa parte não é edificável (APP)."
        )
    if corta_rio:
        avisos.append(
            "Um curso d'água atravessa o lote: a faixa de APP ao longo dele reduz a área útil."
        )
    return avisos


def altura_label(
    faixa_orla: str | None,
    em_centro_historico: bool,
    em_barreira: bool,
    altura_livre: bool | None,
) -> str:
    """Rótulo humano da restrição de altura do lote."""
    if em_centro_historico:
        return "Restrito — IPHAEP (centro histórico)"
    if em_barreira:
        return "Restrito — barreira do Cabo Branco"
    if faixa_orla:
        return f"Faixa da orla ({faixa_orla}) — altura escalonada"
    if altura_livre:
        return "Livre — limitada pelos recuos"
    return "A confirmar"


@dataclass(frozen=True)
class VGVEstimate:
    """Estudo de massa rápido por lote: envelope LUOS × R$/m² de venda do bairro.

    Headline sólido = `vgv_por_pavimento` (não depende de altura). O `vgv_total` usa a
    premissa `pavimentos` (altura em JP é espacial e ainda não modelada por lote).
    """
    preco_m2_venda: float
    eficiencia: float
    pavimentos: int
    area_projecao_m2: float
    area_privativa_pavto_m2: float
    vgv_por_pavimento: float
    area_construida_m2: float
    area_privativa_total_m2: float
    vgv_total: float
    # Faixa (Q1–Q3 do preço): combate a falsa precisão da mediana. None quando sem quartis.
    vgv_por_pavimento_min: float | None
    vgv_por_pavimento_max: float | None
    vgv_total_min: float | None
    vgv_total_max: float | None
    custo_terreno: float | None
    custo_obra_m2: float | None
    custo_obra: float | None
    margem: float | None
    margem_pct: float | None


def estimar_vgv(
    area_projecao_max_m2: float | None,
    preco_m2_venda: float | None,
    pavimentos: int = PAVIMENTOS_PREMISSA_PADRAO,
    eficiencia: float = EFICIENCIA_PADRAO,
    custo_obra_m2: float | None = None,
    custo_terreno: float | None = None,
    preco_m2_q1: float | None = None,
    preco_m2_q3: float | None = None,
) -> VGVEstimate | None:
    """VGV potencial do lote. None se faltar projeção/preço ou premissa inválida.

    VGV/pavto = projeção_térreo × eficiência × R$/m². Total = VGV/pavto × pavimentos.
    Com Q1/Q3 do preço sai uma FAIXA (min/max) — honestidade contra a falsa precisão de
    um único número. Margem só sai com custo de obra (dominante); terreno entra se informado.
    """
    if not area_projecao_max_m2 or area_projecao_max_m2 <= 0:
        return None
    if not preco_m2_venda or preco_m2_venda <= 0:
        return None
    if pavimentos < 1:
        return None

    area_privativa_pavto = area_projecao_max_m2 * eficiencia
    vgv_por_pavimento = area_privativa_pavto * preco_m2_venda
    area_construida = area_projecao_max_m2 * pavimentos
    area_privativa_total = area_privativa_pavto * pavimentos
    vgv_total = vgv_por_pavimento * pavimentos

    vgv_pp_min = area_privativa_pavto * preco_m2_q1 if preco_m2_q1 else None
    vgv_pp_max = area_privativa_pavto * preco_m2_q3 if preco_m2_q3 else None
    vgv_total_min = vgv_pp_min * pavimentos if vgv_pp_min is not None else None
    vgv_total_max = vgv_pp_max * pavimentos if vgv_pp_max is not None else None

    custo_obra = area_construida * custo_obra_m2 if custo_obra_m2 else None
    margem = margem_pct = None
    if custo_obra is not None:
        margem = vgv_total - custo_obra - (custo_terreno or 0)
        margem_pct = margem / vgv_total if vgv_total else None

    return VGVEstimate(
        preco_m2_venda=preco_m2_venda,
        eficiencia=eficiencia,
        pavimentos=pavimentos,
        area_projecao_m2=area_projecao_max_m2,
        area_privativa_pavto_m2=area_privativa_pavto,
        vgv_por_pavimento=vgv_por_pavimento,
        area_construida_m2=area_construida,
        area_privativa_total_m2=area_privativa_total,
        vgv_total=vgv_total,
        vgv_por_pavimento_min=vgv_pp_min,
        vgv_por_pavimento_max=vgv_pp_max,
        vgv_total_min=vgv_total_min,
        vgv_total_max=vgv_total_max,
        custo_terreno=custo_terreno,
        custo_obra_m2=custo_obra_m2,
        custo_obra=custo_obra,
        margem=margem,
        margem_pct=margem_pct,
    )


# ───────── valor residual (involutivo): "quanto pagar" pelo terreno ─────────
# O terreno vale o RESÍDUO do VGV depois de obra, impostos, comercialização, indiretos e a
# margem-alvo. É o inverso do VGV e o número que decide a originação (Job 3 do spec).
@dataclass(frozen=True)
class ResidualEstimate:
    """Máximo a pagar pelo terreno p/ atingir a margem-alvo. Espelha a faixa Q1–Q3 do VGV."""
    custo_obra_m2: float
    margem_alvo: float
    custos_indiretos_pct: float        # soma impostos + comercialização + indiretos (% do VGV)
    # Por pavimento = headline robusto (independe da premissa de altura, espacial em JP).
    residual_por_pavimento: float
    residual_por_pavimento_min: float | None
    residual_por_pavimento_max: float | None
    # Total = sob a premissa de pavimentos.
    residual_total: float
    residual_total_min: float | None
    residual_total_max: float | None
    terreno_pct_vgv: float | None      # residual_total ÷ vgv_total (régua de bolso 15–20%)
    # Barganha (só com anúncio casado): gap entre o que cabe pagar e o preço pedido.
    preco_pedido: float | None
    gap_pct: float | None              # (residual − pedido) ÷ residual ; >0 cabe, <0 caro
    cabe_no_bolso: bool | None


def estimar_residual(
    vgv: VGVEstimate,
    custo_obra_m2: float = CUSTO_OBRA_M2_PADRAO,
    margem_alvo: float = MARGEM_ALVO_PADRAO,
    impostos_pct: float = IMPOSTOS_PCT_PADRAO,
    comercializacao_pct: float = COMERCIALIZACAO_PCT_PADRAO,
    indiretos_pct: float = INDIRETOS_PCT_PADRAO,
    preco_pedido: float | None = None,
) -> ResidualEstimate:
    """Valor residual do terreno a partir de um VGV já estimado (método involutivo).

    residual = VGV × (1 − custos% − margem) − área_construída × custo_obra_m2.
    O custo de obra é FIXO (não depende do preço de venda), então a faixa Q1–Q3 do VGV se
    propaga direto — e pode cruzar o zero (lote inviável no piso da faixa). `gap_pct` só sai
    com preço pedido E residual positivo (barganha sem residual positivo não tem sentido).
    """
    custos_pct = impostos_pct + comercializacao_pct + indiretos_pct
    fator = 1.0 - custos_pct - margem_alvo
    obra_pp = vgv.area_projecao_m2 * custo_obra_m2

    res_pp = vgv.vgv_por_pavimento * fator - obra_pp
    res_total = res_pp * vgv.pavimentos

    res_pp_min = (
        vgv.vgv_por_pavimento_min * fator - obra_pp
        if vgv.vgv_por_pavimento_min is not None else None
    )
    res_pp_max = (
        vgv.vgv_por_pavimento_max * fator - obra_pp
        if vgv.vgv_por_pavimento_max is not None else None
    )
    res_total_min = res_pp_min * vgv.pavimentos if res_pp_min is not None else None
    res_total_max = res_pp_max * vgv.pavimentos if res_pp_max is not None else None

    terreno_pct = res_total / vgv.vgv_total if vgv.vgv_total else None

    gap_pct = cabe = None
    if preco_pedido is not None and res_total > 0:
        gap_pct = (res_total - preco_pedido) / res_total
        cabe = gap_pct >= 0

    return ResidualEstimate(
        custo_obra_m2=custo_obra_m2,
        margem_alvo=margem_alvo,
        custos_indiretos_pct=custos_pct,
        residual_por_pavimento=res_pp,
        residual_por_pavimento_min=res_pp_min,
        residual_por_pavimento_max=res_pp_max,
        residual_total=res_total,
        residual_total_min=res_total_min,
        residual_total_max=res_total_max,
        terreno_pct_vgv=terreno_pct,
        preco_pedido=preco_pedido,
        gap_pct=gap_pct,
        cabe_no_bolso=cabe,
    )


# ───────── preço de referência: comps no RAIO do lote, com fallback p/ o bairro ─────────
# Mediana do bairro inteiro mascara variância intra-bairro (frente-mar × fundo). Preferimos
# a estatística dos comps perto do lote; só caímos no bairro quando o raio tem poucos comps.
N_MIN_RAIO = 5  # mínimo de comps no raio p/ confiar nele em vez do bairro


@dataclass(frozen=True)
class PrecoStats:
    """Estatística de R$/m² de uma amostra de comps (raio do lote OU bairro)."""
    preco_m2: float          # mediana
    q1: float | None
    q3: float | None
    n: int


@dataclass(frozen=True)
class PrecoRef:
    """Preço de referência escolhido + de onde veio (transparência na ficha)."""
    preco_m2: float
    q1: float | None
    q3: float | None
    n: int
    fonte: str               # 'raio' | 'bairro'


def escolher_preco_ref(
    raio: PrecoStats | None,
    bairro: PrecoStats | None,
    n_min: int = N_MIN_RAIO,
) -> PrecoRef | None:
    """Usa o raio quando tem comps suficientes (n ≥ n_min); senão cai no bairro. None se nada."""
    if raio is not None and raio.n >= n_min:
        return PrecoRef(raio.preco_m2, raio.q1, raio.q3, raio.n, "raio")
    if bairro is not None and bairro.n > 0:
        return PrecoRef(bairro.preco_m2, bairro.q1, bairro.q3, bairro.n, "bairro")
    return None


# ───────── IncorpoScore: ranking 0–100 das melhores oportunidades ─────────
# Nota composta de 4 eixos, cada um normalizado 0–1 por função de transferência com âncoras
# EXPLÍCITAS (não percentil) — assim a nota de um lote é estável e calculável sozinha, sem
# depender da coorte. As âncoras seguem o playbook do AREA_LOTE_SUSPEITA_M2: A CALIBRAR com a
# distribuição real de JP (1 query de quantis). Transparência: a ficha mostra a decomposição.
SCORE_W_RENTABILIDADE = 0.35
SCORE_W_APROVEITAMENTO = 0.25
SCORE_W_LOCALIZACAO = 0.25
SCORE_W_CONFIANCA = 0.15

# Âncoras CALIBRADAS contra a distribuição real (Neon, 2026-06-28): 23.329 lotes rankeáveis
# (TERRITORIAL, com zona, área<30k), 77% com preço de bairro. Percentis no servidor.
# aprov_ratio real (proj×0,8×preço_bairro÷área): P10≈1.364 · P50≈1.612 · P90≈3.568 · P95≈4.639.
# Faixa P10→P95 espalha o miolo e só o decil-topo (frente-mar denso) satura.
APROV_VGV_M2_LOW = 1350.0      # VGV/pavto por m² de terreno → nota 0  (≈P10 do estoque real)
APROV_VGV_M2_HIGH = 4600.0     # → nota 1                              (≈P95; antes 4000 já saturava)
# preço/m² por lote (mediana do bairro do lote): P10≈3.100 · P50≈3.516 · P90≈8.920 · P95≈9.504.
# LOW=4000 (valor antigo) ficava ACIMA da mediana → metade dos lotes pontuava 0; corrigido p/ P10.
LOC_PRECO_M2_LOW = 3100.0      # R$/m² de venda do bairro → nota 0      (≈P10 do estoque real)
LOC_PRECO_M2_HIGH = 11000.0    # → nota 1 (acima do P95 de lote; só frente-mar premium satura)
SCORE_GAP_FULL = 0.40          # gap de barganha (±) que satura a rentabilidade
# terreno/VGV (involutivo) chega a ~43% nos lotes viáveis; 15-20% é o NORMAL (benchmark do spec),
# não o teto. Saturar em 0,20 empatava todo o quartil viável → teto em 0,40 reabre a discriminação.
SCORE_TERRENO_PCT_FULL = 0.40  # terreno/VGV que satura a rentabilidade estrutural (sem anúncio)
CONF_N_MIN = 5                 # n de comps → nota 0,3
CONF_N_FULL = 30               # n de comps → nota 1,0
CONF_IQR_FULL = 0.60           # IQR relativo (q3−q1)/mediana que zera a confiança
SCORE_PENALIDADE_ALTURA = 0.70  # multiplicador p/ altura restrita (IPHAEP/barreira)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass(frozen=True)
class ScoreBreakdown:
    """IncorpoScore 0–100 + decomposição (cada eixo 0–10) p/ transparência na ficha."""
    total: float
    rentabilidade: float
    aproveitamento: float
    localizacao: float
    confianca: float
    penalidade_altura: bool


def incorpo_score(
    vgv_por_pavimento: float,
    area_lote_m2: float,
    preco_m2: float,
    n_comps: int,
    terreno_pct_vgv: float | None,
    gap_pct: float | None,
    q1: float | None = None,
    q3: float | None = None,
    em_centro_historico: bool = False,
    em_barreira: bool = False,
) -> ScoreBreakdown:
    """Nota de atratividade do lote. Pressupõe lote ranqueável (VGV/zona; suspeita já filtrada).

    Rentabilidade: gap de barganha (com anúncio) ou terreno/VGV (sem). Aproveitamento: VGV/pavto
    por m² de terreno. Localização: nível de preço (tendência de valorização entra na fase C).
    Confiança: n de comps + aperto do IQR. Altura restrita (IPHAEP/barreira) penaliza o total
    (produto vertical limitado). Eixos em 0–10; total em 0–100.
    """
    if gap_pct is not None:
        rent01 = _clamp01(0.5 + gap_pct / SCORE_GAP_FULL)
    elif terreno_pct_vgv is not None:
        rent01 = _clamp01(terreno_pct_vgv / SCORE_TERRENO_PCT_FULL)
    else:
        rent01 = 0.0

    aprov_ratio = vgv_por_pavimento / area_lote_m2 if area_lote_m2 else 0.0
    aprov01 = _clamp01((aprov_ratio - APROV_VGV_M2_LOW) / (APROV_VGV_M2_HIGH - APROV_VGV_M2_LOW))

    loc01 = _clamp01((preco_m2 - LOC_PRECO_M2_LOW) / (LOC_PRECO_M2_HIGH - LOC_PRECO_M2_LOW))

    n01 = _clamp01(0.3 + (n_comps - CONF_N_MIN) / (CONF_N_FULL - CONF_N_MIN) * 0.7)
    if q1 is not None and q3 is not None and preco_m2:
        iqr01 = _clamp01(1.0 - ((q3 - q1) / preco_m2) / CONF_IQR_FULL)
    else:
        iqr01 = 0.5  # sem quartis → dispersão neutra
    conf01 = (n01 + iqr01) / 2.0

    base = (
        SCORE_W_RENTABILIDADE * rent01
        + SCORE_W_APROVEITAMENTO * aprov01
        + SCORE_W_LOCALIZACAO * loc01
        + SCORE_W_CONFIANCA * conf01
    )
    pen_altura = em_centro_historico or em_barreira
    total = 100.0 * base * (SCORE_PENALIDADE_ALTURA if pen_altura else 1.0)

    return ScoreBreakdown(
        total=total,
        rentabilidade=rent01 * 10.0,
        aproveitamento=aprov01 * 10.0,
        localizacao=loc01 * 10.0,
        confianca=conf01 * 10.0,
        penalidade_altura=pen_altura,
    )
