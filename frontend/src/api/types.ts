// Espelha os modelos da API (src/api/schemas.py).

export interface Viability {
  sigla?: string | null
  nome_zona?: string | null
  to_max_pct?: number | null
  tap_min_pct?: number | null
  area_projecao_max_m2?: number | null
  area_permeavel_min_m2?: number | null
  recuo_frontal_m?: number | null
  recuo_lateral?: string | null
  recuo_fundo?: string | null
  usos_obs?: string | null
}

export interface Restricao {
  faixa_orla?: string | null
  em_centro_historico: boolean
  em_barreira: boolean
  altura_livre?: boolean | null
  altura_label: string
}

export interface Listing {
  anuncio_id: number
  fonte: string
  preco?: number | null
  area_anunc_m2?: number | null
  preco_m2?: number | null
}

export interface LotFicha {
  id: number
  inscricao?: string | null
  setor?: string | null
  quadra?: string | null
  lote?: string | null
  logradouro?: string | null
  bairro?: string | null
  tipo?: string | null
  area_cad_m2?: number | null
  area_geom_m2?: number | null
  centroid?: [number, number] | null
  viability?: Viability | null
  restricao: Restricao
  listing?: Listing | null
}

// Propriedades de cada feature no GeoJSON de /api/lots
export interface LotProperties {
  id: number
  logradouro?: string | null
  bairro?: string | null
  tipo?: string | null
  area_m2?: number | null
  area_projecao_max_m2?: number | null
  sigla?: string | null
  a_venda: boolean
  preco?: number | null
  preco_m2?: number | null
}
