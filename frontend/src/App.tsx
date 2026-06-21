import { useState } from 'react'
import { FiltersBar } from './components/FiltersBar'
import { MapView } from './components/MapView'
import { ResultsList } from './components/ResultsList'
import { LotFichaPanel } from './components/LotFichaPanel'
import { LandbankBoard } from './components/LandbankBoard'
import { useAsync } from './hooks/useApi'
import { getLot, listBairros, listLots, type LotFilters } from './api/client'

type View = 'explorar' | 'landbank'

export default function App() {
  const [view, setView] = useState<View>('explorar')
  const [filters, setFilters] = useState<LotFilters>({
    bairro: '',
    onlyVacant: true,
    aVenda: false,
    areaMin: '',
    areaMax: '',
    sort: 'none',
  })
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const bairros = useAsync(() => listBairros(), [])
  const lots = useAsync(
    () => listLots(filters),
    [filters.bairro, filters.onlyVacant, filters.aVenda, filters.areaMin, filters.areaMax, filters.sort],
  )
  const ficha = useAsync(
    () => (selectedId == null ? Promise.resolve(null) : getLot(selectedId)),
    [selectedId],
  )

  const count = lots.data?.features.length ?? 0

  return (
    <div className="app">
      <header className="topbar">
        <h1 className="brand">
          Incorpo<span>Data</span>
        </h1>
        <nav className="viewnav">
          <button className={view === 'explorar' ? 'on' : ''} onClick={() => setView('explorar')}>
            Explorar
          </button>
          <button className={view === 'landbank' ? 'on' : ''} onClick={() => setView('landbank')}>
            Landbank
          </button>
        </nav>
        {view === 'explorar' && (
          <FiltersBar bairros={bairros.data ?? []} value={filters} onChange={setFilters} />
        )}
      </header>
      {view === 'explorar' ? (
        <main className="main">
          <MapView data={lots.data} selectedId={selectedId} onSelect={setSelectedId} />
          <aside className="panel">
            {selectedId != null ? (
              <LotFichaPanel
                lot={ficha.data}
                loading={ficha.loading}
                error={ficha.error}
                onBack={() => setSelectedId(null)}
              />
            ) : (
              <ResultsList
                data={lots.data}
                loading={lots.loading}
                error={lots.error}
                count={count}
                sort={filters.sort}
                selectedId={selectedId}
                onSelect={setSelectedId}
              />
            )}
          </aside>
        </main>
      ) : (
        <main className="main">
          <LandbankBoard
            onOpenLot={(id) => {
              setSelectedId(id)
              setView('explorar')
            }}
          />
        </main>
      )}
    </div>
  )
}
