import type { FeatureCollection } from 'geojson'
import type { LandbankItem, LotFicha, Oportunidade, User } from './types'

const BASE = '/api'

// ───────── auth (token de dev por ora; UI de login fica p/ depois) ─────────
const TOKEN_KEY = 'incorpodata_token'

export function getToken(): string | null {
  const env = (import.meta as unknown as { env?: Record<string, string> }).env
  return localStorage.getItem(TOKEN_KEY) ?? env?.VITE_DEV_TOKEN ?? null
}
export function setToken(t: string): void {
  localStorage.setItem(TOKEN_KEY, t)
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

function authHeaders(): Record<string, string> {
  const t = getToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

async function json<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return (await res.json()) as T
}

/** Request autenticada (landbank). Extrai `detail` do erro da API quando houver. */
async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { ...(init?.headers ?? {}), ...authHeaders() },
  })
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
    sort: f.sort,
  })
  if (f.areaMin.trim()) p.set('area_min', f.areaMin.trim())
  if (f.areaMax.trim()) p.set('area_max', f.areaMax.trim())
  return json<FeatureCollection>(`${BASE}/lots?${p.toString()}`)
}

export const getLot = (id: number) => json<LotFicha>(`${BASE}/lots/${id}`)

// Ranking de oportunidades por valor residual (feature paga → request autenticada).
export const listOportunidades = (bairro: string, limit = 20) =>
  req<Oportunidade[]>(`${BASE}/oportunidades?bairro=${encodeURIComponent(bairro)}&limit=${limit}`)

// PDF da ficha (rota pública; abre direto no navegador).
export const lotPdfUrl = (id: number) => `${BASE}/lots/${id}/pdf`

// ───────── auth (register / login / me) ─────────
// `register` cria a conta mas não devolve token; o fluxo chama `login` em seguida.
export const register = (email: string, senha: string, nome?: string, codigo?: string) =>
  req<User>(`${BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email,
      senha,
      nome: nome || undefined,
      invite_code: codigo || undefined,
    }),
  })

// O backend usa OAuth2PasswordRequestForm → corpo form-urlencoded (username/password).
export async function login(email: string, senha: string): Promise<User> {
  const body = new URLSearchParams({ username: email, password: senha })
  const { access_token } = await req<{ access_token: string }>(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  })
  setToken(access_token)
  return me()
}

export const me = () => req<User>(`${BASE}/auth/me`)

// ───────── landbank (pipeline de lotes salvos, escopado por usuário) ─────────
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

export const listLandbank = () => req<LandbankItem[]>(`${BASE}/landbank`)

export const addLandbank = (loteId: number) =>
  req<LandbankItem>(`${BASE}/landbank`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lote_id: loteId }),
  })

export const patchLandbank = (id: number, body: { estagio?: Estagio; notas?: string }) =>
  req<LandbankItem>(`${BASE}/landbank/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

export const removeLandbank = (id: number) =>
  req<void>(`${BASE}/landbank/${id}`, { method: 'DELETE' })
