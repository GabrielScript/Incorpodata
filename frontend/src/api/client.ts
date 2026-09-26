import type { FeatureCollection } from 'geojson'
import type { LandbankItem, LotFicha, Oportunidade } from './types'

const BASE = '/api'

// App aberto: quem tem o link acessa tudo, sem login. A API de auth (/api/auth) e o landbank
// por conta (/api/landbank) seguem no backend, sem uso pelo frontend — voltam se os planos
// pagos forem ligados.

async function json<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return (await res.json()) as T
}

/** Request que extrai `detail` do erro da API quando houver (ex.: 402 do gate de planos). */
async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (res.status === 204) return undefined as T
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const j = (await res.json()) as { detail?: string }
      if (j?.detail) detail = j.detail
    } catch {
      /* corpo não-JSON */
    }
    throw new Error(detail)
  }
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
  aVenda: boolean // só lotes com anúncio ativo casado (terreno ou casa); com onlyVacant = o alvo
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

/** GeoJSON dos lotes + `truncado`: o recorte passou do teto da API e veio cortado. */
export type LotCollection = FeatureCollection & { truncado?: boolean }

/** Recorte dos filtros (sem a ordenação): o que a lista e os tiles do mapa têm em comum. */
function recorteParams(f: Omit<LotFilters, 'sort'>): URLSearchParams {
  const p = new URLSearchParams({
    bairro: f.bairro,
    only_vacant: String(f.onlyVacant),
    a_venda: String(f.aVenda),
  })
  if (f.areaMin.trim()) p.set('area_min', f.areaMin.trim())
  if (f.areaMax.trim()) p.set('area_max', f.areaMax.trim())
  return p
}

export function listLots(f: LotFilters): Promise<LotCollection> {
  const p = recorteParams(f)
  p.set('sort', f.sort)
  return json<LotCollection>(`${BASE}/lots?${p.toString()}`)
}

/** URL-modelo dos tiles vetoriais (MVT) dos lotes no recorte dos filtros. Absoluta: o worker do
 *  MapLibre não resolve URL relativa. Sem `sort`: reordenar a lista não invalida o cache. */
export const lotTilesUrl = (f: Omit<LotFilters, 'sort'>) =>
  `${window.location.origin}${BASE}/tiles/lotes/{z}/{x}/{y}.pbf?${recorteParams(f).toString()}`

export const getLot = (id: number) => json<LotFicha>(`${BASE}/lots/${id}`)

// Ranking de oportunidades por valor residual (público enquanto o gate de planos está off).
export const listOportunidades = (bairro: string, limit = 20) =>
  req<Oportunidade[]>(`${BASE}/oportunidades?bairro=${encodeURIComponent(bairro)}&limit=${limit}`)

// PDF da ficha (rota pública; abre direto no navegador).
export const lotPdfUrl = (id: number) => `${BASE}/lots/${id}/pdf`

// ───────── landbank (pipeline de lotes salvos, no navegador de cada um) ─────────
// Sem login, cada pessoa tem a própria lista no localStorage deste navegador: ninguém vê a
// lista de ninguém (construtoras concorrentes usam o mesmo link). Não sincroniza entre
// aparelhos e some se o navegador limpar os dados do site. Async p/ manter a assinatura da
// versão por API — o LandbankBoard não muda.
export const ESTAGIOS = [
  'triagem',
  'analise',
  'opcao',
  'due_diligence',
  'adquirido',
  'descartado',
] as const
export type Estagio = (typeof ESTAGIOS)[number]

export const ESTAGIO_LABELS: Record<Estagio, string> = {
  triagem: 'Triagem',
  analise: 'Análise',
  opcao: 'Opção',
  due_diligence: 'Due diligence',
  adquirido: 'Adquirido',
  descartado: 'Descartado',
}

const LANDBANK_KEY = 'incorpodata_landbank'

function lbRead(): LandbankItem[] {
  try {
    const raw = localStorage.getItem(LANDBANK_KEY)
    const v: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(v) ? (v as LandbankItem[]) : []
  } catch {
    return [] // storage bloqueado (modo anônimo/política) ou JSON corrompido → lista vazia
  }
}

function lbWrite(items: LandbankItem[]): void {
  try {
    localStorage.setItem(LANDBANK_KEY, JSON.stringify(items))
  } catch {
    throw new Error('o navegador não deixou salvar (modo anônimo ou armazenamento cheio)')
  }
}

export const listLandbank = async (): Promise<LandbankItem[]> => lbRead()

/** Salva o lote com logradouro/bairro/área da ficha (o board não re-consulta a API). */
export async function addLandbank(
  lot: Pick<LotFicha, 'id' | 'logradouro' | 'bairro' | 'area_geom_m2'>,
): Promise<LandbankItem> {
  const items = lbRead()
  const ja = items.find((i) => i.lote_id === lot.id)
  if (ja) return ja // idempotente, como a API era: lote já salvo não duplica
  const item: LandbankItem = {
    id: items.reduce((m, i) => Math.max(m, i.id), 0) + 1,
    lote_id: lot.id,
    estagio: 'triagem',
    notas: null,
    logradouro: lot.logradouro ?? null,
    bairro: lot.bairro ?? null,
    area_geom_m2: lot.area_geom_m2 ?? null,
  }
  lbWrite([...items, item])
  return item
}

export async function patchLandbank(
  id: number,
  body: { estagio?: Estagio; notas?: string },
): Promise<LandbankItem> {
  const items = lbRead()
  const i = items.findIndex((x) => x.id === id)
  if (i < 0) throw new Error('este lote não está mais no landbank')
  items[i] = { ...items[i], ...body }
  lbWrite(items)
  return items[i]
}

export async function removeLandbank(id: number): Promise<void> {
  lbWrite(lbRead().filter((x) => x.id !== id))
}
