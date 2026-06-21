"""Lógica pura da ficha de viabilidade (sem DB) — o moat, por isso testada.

Em João Pessoa a altura/nº de pavimentos é ESPACIAL (faixa de 500m da orla + IPHAEP +
barreira do Cabo Branco), não vem da zona. Aqui traduzimos as flags por lote
(geo.lote_restricao) num rótulo legível. Ordem = mais restritivo primeiro.
"""
from __future__ import annotations

from dataclasses import dataclass

# Premissas do estudo de massa (o incorporador ajusta; aqui são defaults transparentes).
EFICIENCIA_PADRAO = 0.80          # área privativa ÷ área construída (desconta circulação/comum)
PAVIMENTOS_PREMISSA_PADRAO = 4    # altura em JP é ESPACIAL; sem a camada carregada, premissa baixa


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
