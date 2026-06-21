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

export interface VGV {
  preco_m2_venda: number
  preco_m2_q1?: number | null
  preco_m2_q3?: number | null
  n_comps: number
  fonte_preco: string // 'raio' | 'bairro'
  eficiencia: number
  pavimentos: number
  area_projecao_m2: number
  area_privativa_pavto_m2: number
  vgv_por_pavimento: number
  vgv_por_pavimento_min?: number | null
  vgv_por_pavimento_max?: number | null
  area_construida_m2: number
  area_privativa_total_m2: number
  vgv_total: number
  vgv_total_min?: number | null
  vgv_total_max?: number | null
  custo_terreno?: number | null
  custo_obra_m2?: number | null
  custo_obra?: number | null
  margem?: number | null
  margem_pct?: number | null
  premissas: string
}

export interface LandbankItem {
  id: number
  lote_id: number
  estagio: string
  notas?: string | null
  logradouro?: string | null
  bairro?: string | null
  area_geom_m2?: number | null
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
  vgv?: VGV | null
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
