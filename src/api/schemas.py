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
    centroid: list[float] | None = None  # [lng, lat] WGS84, p/ centralizar o mapa
    viability: Viability | None = None
    restricao: Restricao
    listing: Listing | None = None


# ───────── auth ─────────
class RegisterIn(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=8, max_length=128)
    nome: str | None = Field(default=None, max_length=120)


class UserOut(BaseModel):
    id: int
    email: EmailStr
    nome: str | None = None


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
