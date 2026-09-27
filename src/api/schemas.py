"""Modelos de request/response da API (Pydantic v2)."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


# ───────── viabilidade / ficha ─────────
class Viability(BaseModel):
    sigla: str | None = None
    nome_zona: str | None = None
    to_max_pct: float | None = None
    tap_min_pct: float | None = None
    area_projecao_max_m2: float | None = None
    area_permeavel_min_m2: float | None = None
    recuo_frontal_m: float | None = None
    recuo_lateral: str | None = None
    recuo_fundo: str | None = None
    usos_obs: str | None = None


class Restricao(BaseModel):
    faixa_orla: str | None = None
    em_centro_historico: bool = False
    em_barreira: bool = False
    altura_livre: bool | None = None
    altura_label: str


class Listing(BaseModel):
    anuncio_id: int
    fonte: str
    preco: float | None = None
    area_anunc_m2: float | None = None
    preco_m2: float | None = None
    # url NÃO exposta aqui (LGPD): revelar contato sob demanda em endpoint próprio.


class VGV(BaseModel):
    """Estudo de massa rápido: envelope LUOS × R$/m² de venda (comps no raio do lote)."""
    preco_m2_venda: float          # mediana dos comps de Apartamento (raio ou bairro)
    preco_m2_q1: float | None = None   # 1º quartil → piso da faixa
    preco_m2_q3: float | None = None   # 3º quartil → teto da faixa
    n_comps: int                   # tamanho da amostra (robustez da mediana)
    fonte_preco: str = "bairro"    # 'raio' (micro-localização) | 'bairro' (fallback)
    eficiencia: float              # premissa: área privativa ÷ construída
    pavimentos: int                # premissa (altura em JP é espacial, ainda não por lote)
    area_projecao_m2: float        # TO_máx × área do lote (footprint)
    area_privativa_pavto_m2: float
    vgv_por_pavimento: float       # headline sólido (independe de altura)
    vgv_por_pavimento_min: float | None = None   # faixa Q1–Q3 (contra falsa precisão)
    vgv_por_pavimento_max: float | None = None
    area_construida_m2: float
    area_privativa_total_m2: float
    vgv_total: float               # sob a premissa de pavimentos
    vgv_total_min: float | None = None
    vgv_total_max: float | None = None
    custo_terreno: float | None = None
    custo_obra_m2: float | None = None
    custo_obra: float | None = None
    margem: float | None = None
    margem_pct: float | None = None
    premissas: str


class Residual(BaseModel):
    """Valor residual do terreno (involutivo): o máximo a pagar p/ a margem-alvo."""
    custo_obra_m2: float           # premissa (calibrar ao CUB-PB) — a mais sensível
    margem_alvo: float             # lucro mínimo sobre VGV exigido do negócio
    custos_indiretos_pct: float    # impostos + comercialização + indiretos (% do VGV)
    residual_por_pavimento: float  # headline robusto (independe da premissa de altura)
    residual_por_pavimento_min: float | None = None  # faixa Q1–Q3 (pode cruzar o zero)
    residual_por_pavimento_max: float | None = None
    residual_total: float          # sob a premissa de pavimentos
    residual_total_min: float | None = None
    residual_total_max: float | None = None
    terreno_pct_vgv: float | None = None  # residual ÷ VGV (régua de bolso 15–20%)
    preco_pedido: float | None = None     # do anúncio casado, quando existe
    gap_pct: float | None = None          # (residual − pedido) ÷ residual: barganha
    cabe_no_bolso: bool | None = None
    premissas: str


class Score(BaseModel):
    """IncorpoScore 0–100 + decomposição (eixos 0–10). Relativo às premissas, preliminar."""
    total: float
    rentabilidade: float
    aproveitamento: float
    localizacao: float
    confianca: float
    penalidade_altura: bool = False
    nota_metodo: str


class LotFicha(BaseModel):
    id: int
    inscricao: str | None = None
    setor: str | None = None
    quadra: str | None = None
    lote: str | None = None
    logradouro: str | None = None
    bairro: str | None = None
    tipo: str | None = None
    area_cad_m2: float | None = None
    area_geom_m2: float | None = None
    # Guarda de plausibilidade: área grande demais p/ lote urbano (gleba/ZEPA). VGV suprimido.
    geometria_suspeita: bool = False
    geometria_aviso: str | None = None
    centroid: list[float] | None = None  # [lng, lat] WGS84, p/ centralizar o mapa
    viability: Viability | None = None
    restricao: Restricao
    listing: Listing | None = None
    vgv: VGV | None = None
    # Tier free: VGV existe mas é suprimido como teaser → front mostra card "assine p/ ver".
    vgv_bloqueado: bool = False
    residual: Residual | None = None
    # Tier free: residual (decisão "quanto pagar") suprimido como teaser, igual ao VGV.
    residual_bloqueado: bool = False
    score: Score | None = None
    score_bloqueado: bool = False


class Oportunidade(BaseModel):
    """Linha do ranking de oportunidades (/api/oportunidades) — ficha-lite ordenável."""
    lot_id: int
    logradouro: str | None = None
    bairro: str | None = None
    area_m2: float | None = None
    vgv_total: float
    residual_total: float
    terreno_pct_vgv: float | None = None
    gap_pct: float | None = None
    cabe_no_bolso: bool | None = None
    score: Score


# ───────── auth ─────────
class RegisterIn(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=8, max_length=128)
    nome: str | None = Field(default=None, max_length=120)
    invite_code: str | None = Field(default=None, max_length=200)  # registro por convite


class UserOut(BaseModel):
    id: int
    email: EmailStr
    nome: str | None = None
    plano: str = "free"  # tier de assinatura → front mostra/esconde features pagas


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ───────── landbank ─────────
class LandbankIn(BaseModel):
    lote_id: int


class LandbankPatch(BaseModel):
    estagio: str | None = None
    notas: str | None = Field(default=None, max_length=4000)


class LandbankItem(BaseModel):
    id: int
    lote_id: int
    estagio: str
    notas: str | None = None
    logradouro: str | None = None
    bairro: str | None = None
    area_geom_m2: float | None = None
