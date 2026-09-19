import { useEffect, useState } from 'react'
import { FiltersBar } from './components/FiltersBar'
import { MapView } from './components/MapView'
import { ResultsList } from './components/ResultsList'
import { LotFichaPanel } from './components/LotFichaPanel'
import { LandbankBoard } from './components/LandbankBoard'
import { OportunidadesView } from './components/OportunidadesView'
import { AuthModal } from './components/AuthModal'
import { useAsync } from './hooks/useApi'
import { clearToken, getLot, getToken, listBairros, listLots, me, type LotFilters } from './api/client'
import type { User } from './api/types'

type View = 'explorar' | 'oportunidades' | 'landbank'

export default function App() {
  const [view, setView] = useState<View>('oportunidades')
  const [filters, setFilters] = useState<LotFilters>({
    bairro: '',
    onlyVacant: true,
    areaMin: '',
    areaMax: '',
    sort: 'none',
  })
  const [selectedId, setSelectedId] = useState<number | null>(null)

  // ── auth ──
  const [user, setUser] = useState<User | null>(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [authOpen, setAuthOpen] = useState(false)

  // Token salvo? Valida em /me (cobre token expirado/revogado).
  useEffect(() => {
    if (!getToken()) {
      setAuthChecked(true)
      return
    }
    me()
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setAuthChecked(true))
  }, [])

  function logout() {
    clearToken()
    setUser(null)
    setView('oportunidades')
  }

  const bairros = useAsync(() => listBairros(), [])
  const lots = useAsync(
    () => listLots(filters),
    [filters.bairro, filters.onlyVacant, filters.areaMin, filters.areaMax, filters.sort],
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
          <button
            className={view === 'oportunidades' ? 'on' : ''}
            onClick={() => setView('oportunidades')}
          >
            Oportunidades
          </button>
          <button className={view === 'landbank' ? 'on' : ''} onClick={() => setView('landbank')}>
            Landbank
          </button>
        </nav>
        {view !== 'landbank' && (
          <FiltersBar bairros={bairros.data ?? []} value={filters} onChange={setFilters} />
        )}
        {authChecked && (
          <div className="auth-slot">
            {user ? (
              <>
                <span className="user-chip" title={user.email}>
                  {user.email}
                </span>
                <button className="linkbtn" onClick={logout}>
                  Sair
                </button>
              </>
            ) : (
              <button className="btn ghost sm" onClick={() => setAuthOpen(true)}>
                Entrar
              </button>
            )}
          </div>
        )}
      </header>
      {view === 'explorar' && (
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
      )}
      {view === 'oportunidades' && (
        <main className="main">
          <OportunidadesView
            bairro={filters.bairro}
            authed={!!user}
            onRequireAuth={() => setAuthOpen(true)}
            onOpenLot={(id) => {
              setSelectedId(id)
              setView('explorar')
            }}
          />
        </main>
      )}
      {view === 'landbank' && (
        <main className="main">
          <LandbankBoard
            authed={!!user}
            onRequireAuth={() => setAuthOpen(true)}
            onOpenLot={(id) => {
              setSelectedId(id)
              setView('explorar')
            }}
          />
        </main>
      )}

      {authOpen && (
        <AuthModal
          onClose={() => setAuthOpen(false)}
          onAuthed={(u) => {
            setUser(u)
            setAuthOpen(false)
          }}
        />
      )}
    </div>
  )
}
