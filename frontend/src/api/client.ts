import type { FeatureCollection } from 'geojson'
import type { LotFicha } from './types'

const BASE = '/api'

async function json<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return (await res.json()) as T
}

export type LotSort =
  | 'none'
  | 'area_desc'
  | 'area_asc'
  | 'proj_desc'
  | 'proj_asc'
  | 'preco_asc'
  | 'preco_desc'
  | 'preco_m2_asc'
  | 'preco_m2_desc'

export interface LotFilters {
  bairro: string // '' = todos os bairros
  onlyVacant: boolean
  aVenda: boolean
  areaMin: string // texto do input; vazio = sem limite
  areaMax: string
  sort: LotSort
}

// Rótulos legíveis da ordenação (cabeçalho da lista mostra qual está ativa).
export const SORT_LABELS: Record<LotSort, string> = {
  none: 'ordem padrão',
  area_desc: 'maior área',
  area_asc: 'menor área',
  proj_desc: 'maior projeção no térreo',
  proj_asc: 'menor projeção no térreo',
  preco_asc: 'menor preço',
  preco_desc: 'maior preço',
  preco_m2_asc: 'menor R$/m²',
  preco_m2_desc: 'maior R$/m²',
}

export const listBairros = () => json<string[]>(`${BASE}/bairros`)

export function listLots(f: LotFilters): Promise<FeatureCollection> {
  const p = new URLSearchParams({
    bairro: f.bairro,
    only_vacant: String(f.onlyVacant),
    a_venda: String(f.aVenda),
    sort: f.sort,
  })
  if (f.areaMin.trim()) p.set('area_min', f.areaMin.trim())
  if (f.areaMax.trim()) p.set('area_max', f.areaMax.trim())
  return json<FeatureCollection>(`${BASE}/lots?${p.toString()}`)
}

export const getLot = (id: number) => json<LotFicha>(`${BASE}/lots/${id}`)
