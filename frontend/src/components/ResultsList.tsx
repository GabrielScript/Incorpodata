import { memo } from 'react'
import type { FeatureCollection } from 'geojson'
import type { LotProperties } from '../api/types'
import { SORT_LABELS, type LotSort } from '../api/client'

const nf0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 })
const fmtM2 = (v: number) => `${nf0.format(v)} m²`

interface Props {
  data: FeatureCollection | null
  loading: boolean
  error: Error | null
  count: number
  sort: LotSort
  selectedId: number | null
  onSelect: (id: number) => void
}

export function ResultsList({ data, loading, error, count, sort, selectedId, onSelect }: Props) {
  if (loading) return <div className="state">Carregando lotes…</div>
  if (error)
    return <div className="state error">Erro: {error.message}. O backend está no ar? (uvicorn)</div>
  if (!data || count === 0)
    return <div className="state">Nenhum lote. Ajuste os filtros ou carregue os dados do Filipeia.</div>

  return (
    <div className="results">
      <div className="results-head">
        <span>
          {count} lote{count === 1 ? '' : 's'}
        </span>
        {sort !== 'none' && <span className="results-sort">↓ {SORT_LABELS[sort]}</span>}
      </div>
      <ul className="results-list">
        {data.features.map((f) => {
          const p = f.properties as unknown as LotProperties
          const id = Number(f.id ?? p.id)
          return <ResultRow key={id} id={id} p={p} active={id === selectedId} onSelect={onSelect} />
        })}
      </ul>
    </div>
  )
}

const ResultRow = memo(function ResultRow({
  id,
  p,
  active,
  onSelect,
}: {
  id: number
  p: LotProperties
  active: boolean
  onSelect: (id: number) => void
}) {
  return (
    <li>
      <button className={`row${active ? ' active' : ''}`} onClick={() => onSelect(id)}>
        <span className="row-main">{p.logradouro ?? `Lote ${id}`}</span>
        <span className="row-sub">
          {p.area_m2 != null && <>{fmtM2(p.area_m2)} · </>}
          {p.sigla ?? 's/ zona'}
        </span>
        {p.area_projecao_max_m2 != null && (
          <span className="row-proj">cabe ~{fmtM2(p.area_projecao_max_m2)} no térreo</span>
        )}
      </button>
    </li>
  )
})
