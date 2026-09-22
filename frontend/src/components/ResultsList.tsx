import { memo, useEffect, useState } from 'react'
import type { LotProperties } from '../api/types'
import { SORT_LABELS, type LotCollection, type LotSort } from '../api/client'

const nf0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 })
const fmtM2 = (v: number) => `${nf0.format(v)} m²`

// Linhas desenhadas por vez. A cidade inteira são ~24 mil lotes: tudo de uma vez travava a
// aba ~10 s (e de novo a cada "← resultados"). O mapa segue mostrando o recorte inteiro.
const PAGINA = 500

interface Props {
  data: LotCollection | null
  loading: boolean
  error: Error | null
  count: number
  sort: LotSort
  selectedId: number | null
  onSelect: (id: number) => void
}

export function ResultsList({ data, loading, error, count, sort, selectedId, onSelect }: Props) {
  const [shown, setShown] = useState(PAGINA)
  useEffect(() => setShown(PAGINA), [data]) // recorte novo recomeça do topo

  if (loading) return <div className="state">Carregando lotes…</div>
  if (error)
    return <div className="state error">Erro: {error.message}. O backend está no ar? (uvicorn)</div>
  if (!data || count === 0)
    return <div className="state">Nenhum lote. Ajuste os filtros ou carregue os dados do Filipeia.</div>

  return (
    <div className="results">
      <div className="results-head">
        <span>
          {nf0.format(count)} lote{count === 1 ? '' : 's'}
        </span>
        {sort !== 'none' && <span className="results-sort">↓ {SORT_LABELS[sort]}</span>}
      </div>
      {data.truncado && (
        <div className="results-note">
          Recorte grande demais: só os primeiros {nf0.format(count)} lotes vieram. Escolha um
          bairro ou marque “Só vagos” para ver todos.
        </div>
      )}
      <ul className="results-list">
        {data.features.slice(0, shown).map((f) => {
          const p = f.properties as unknown as LotProperties
          const id = Number(f.id ?? p.id)
          return <ResultRow key={id} id={id} p={p} active={id === selectedId} onSelect={onSelect} />
        })}
      </ul>
      {count > shown && (
        <button className="results-more" onClick={() => setShown((s) => s + PAGINA)}>
          Mostrar mais {nf0.format(Math.min(PAGINA, count - shown))} · {nf0.format(shown)} de{' '}
          {nf0.format(count)}
        </button>
      )}
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
