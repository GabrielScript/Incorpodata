"""Planos do IncorpoData — fonte ÚNICA de preço e limites (negócio + gate técnico).

Modelo de receita: assinatura por construtora em 3 tiers + add-ons. Cada feature paga
da plataforma vira um limite aqui; o gate em src/api lê SÓ deste módulo (não espalha
regra de plano pelo código). Preços em R$/mês — números de partida, ajustáveis sem
tocar na lógica de gate.

Drivers de upsell (do mais forte ao mais fraco):
  1. escopo geográfico (municípios liberados)  → maior alavanca de preço
  2. VGV detalhado (faixa Q1–Q3 + comps)        → o "número que vai ao comitê"
  3. ficha em PDF (laudo levável)               → consumível
  4. landbank (nº de lotes salvos) e assentos   → expansão dentro da conta

Add-ons (cobrança avulsa, ver ADDONS): município extra, pacote de fichas PDF, assento extra.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

FREE = "free"
PRO = "pro"
ENTERPRISE = "enterprise"


@dataclass(frozen=True)
class Plan:
    codigo: str
    nome: str                       # rótulo comercial
    preco_mes: int | None           # R$/mês; None = sob consulta
    assentos: int | None            # usuários incluídos; None = ilimitado
    municipios: tuple[str, ...] | None  # escopo liberado; None = todos
    landbank_max: int | None        # lotes salvos; None = ilimitado
    vgv_detalhado: bool             # faixa Q1–Q3 + comps + VGV total (vs. só teaser)
    pdf_mes: int | None             # fichas PDF/mês; 0 = bloqueado, None = ilimitado
    api: bool                       # acesso programático


# ───────── tiers ─────────
PLANS: dict[str, Plan] = {
    FREE: Plan(
        codigo=FREE,
        nome="Explorar",
        preco_mes=0,
        assentos=1,
        municipios=("João Pessoa",),
        landbank_max=5,
        vgv_detalhado=False,        # vê o mapa e a ficha básica; VGV vem como teaser bloqueado
        pdf_mes=0,
        api=False,
    ),
    PRO: Plan(
        codigo=PRO,
        nome="Pro",
        preco_mes=2500,
        assentos=5,
        municipios=("João Pessoa",),
        landbank_max=None,
        vgv_detalhado=True,
        pdf_mes=30,
        api=False,
    ),
    ENTERPRISE: Plan(
        codigo=ENTERPRISE,
        nome="Enterprise",
        preco_mes=None,             # multi-região + API → preço sob consulta
        assentos=None,
        municipios=None,
        landbank_max=None,
        vgv_detalhado=True,
        pdf_mes=None,
        api=True,
    ),
}

# ───────── add-ons (cobrança avulsa) ─────────
# Preços de partida; metering real (consumo/mês) é evolução — hoje o gate é por acesso.
ADDONS = {
    "municipio_extra": {"nome": "Município/região adicional", "preco_mes": 900},
    "pacote_fichas_pdf": {"nome": "Pacote de 25 fichas PDF (excedente)", "preco": 250},
    "assento_extra": {"nome": "Assento adicional", "preco_mes": 300},
}


def enforcement_on() -> bool:
    """Gate de planos ligado? Default DESLIGADO (fase demo: tudo liberado).
    Liga em produção com PLANS_ENFORCED=1 (ou true/yes) quando começar a cobrar."""
    return os.getenv("PLANS_ENFORCED", "").strip().lower() in {"1", "true", "yes"}


def limits_for(plano: str | None) -> Plan:
    """Limites do plano. Com o gate DESLIGADO (demo) todo mundo enxerga ENTERPRISE
    (full). Ligado: plano real; entrada desconhecida/None → FREE (default seguro)."""
    if not enforcement_on():
        return PLANS[ENTERPRISE]
    return PLANS.get(plano or FREE, PLANS[FREE])
