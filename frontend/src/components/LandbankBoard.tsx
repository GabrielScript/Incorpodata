import { useEffect, useState } from 'react'
import type { LandbankItem } from '../api/types'
import {
  ESTAGIOS,
  ESTAGIO_LABELS,
  type Estagio,
  listLandbank,
  patchLandbank,
  removeLandbank,
} from '../api/client'

const nf0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 })
const m2 = (v?: number | null) => (v == null ? '—' : `${nf0.format(v)} m²`)

interface Props {
  authed: boolean
  onRequireAuth: () => void
  onOpenLot: (id: number) => void
}

export function LandbankBoard({ authed, onRequireAuth, onOpenLot }: Props) {
  const [items, setItems] = useState<LandbankItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function reload() {
    setLoading(true)
    try {
      setItems(await listLandbank())
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  // Carrega só quando autenticado; re-carrega ao logar.
  useEffect(() => {
    if (authed) void reload()
    else setItems(null)
  }, [authed])

  if (!authed) {
    return (
      <div className="lb-empty">
        <strong>Entre para usar o landbank.</strong>
        <p>
          O landbank é o seu pipeline de terrenos — cada lote salvo fica na sua conta e visível só
          para você.
        </p>
        <button className="btn" onClick={onRequireAuth}>
          Entrar ou criar conta
        </button>
      </div>
    )
  }
  if (loading && items === null) return <div className="state">Carregando landbank…</div>
  if (error) {
    return (
      <div className="lb-empty">
        <strong>Não foi possível carregar o landbank.</strong>
        <div className="state error">Erro: {error}</div>
        <button className="btn" onClick={() => void reload()}>
          tentar de novo
        </button>
      </div>
    )
  }

  const list = items ?? []
  const total = list.length

  return (
    <div className="lb">
      <div className="lb-head">
        Landbank · <strong>{total}</strong> {total === 1 ? 'lote salvo' : 'lotes salvos'}
      </div>
      {total === 0 ? (
        <div className="lb-empty">
          <strong>Nenhum lote salvo ainda.</strong>
          <p>Em Explorar, abra a ficha de um lote e clique em “+ landbank”.</p>
        </div>
      ) : (
        <div className="lb-board">
          {ESTAGIOS.map((stage) => {
            const col = list.filter((i) => i.estagio === stage)
            return (
              <div className="lb-col" key={stage}>
                <div className="lb-col-h">
                  {ESTAGIO_LABELS[stage]} <span>{col.length}</span>
                </div>
                {col.map((item) => (
                  <LbCard key={item.id} item={item} onChanged={reload} onOpenLot={onOpenLot} />
                ))}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function LbCard({
  item,
  onChanged,
  onOpenLot,
}: {
  item: LandbankItem
  onChanged: () => Promise<void>
  onOpenLot: (id: number) => void
}) {
  const [notas, setNotas] = useState(item.notas ?? '')
  const [busy, setBusy] = useState(false)

  async function move(estagio: Estagio) {
    setBusy(true)
    try {
      await patchLandbank(item.id, { estagio })
      await onChanged()
    } finally {
      setBusy(false)
    }
  }

  async function saveNotas() {
    if ((item.notas ?? '') === notas) return
    setBusy(true)
    try {
      await patchLandbank(item.id, { notas })
      await onChanged()
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!confirm('Remover este lote do landbank?')) return
    setBusy(true)
    try {
      await removeLandbank(item.id)
      await onChanged()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="lb-card" aria-busy={busy}>
      <button className="lb-card-title" onClick={() => onOpenLot(item.lote_id)} title="ver no mapa">
        {item.logradouro ?? `Lote ${item.lote_id}`}
      </button>
      <div className="lb-card-sub">
        {item.bairro ?? '—'} · {m2(item.area_geom_m2)} · #{item.lote_id}
      </div>
      <select
        className="lb-stage"
        value={item.estagio}
        disabled={busy}
        onChange={(e) => void move(e.target.value as Estagio)}
      >
        {ESTAGIOS.map((s) => (
          <option key={s} value={s}>
            {ESTAGIO_LABELS[s]}
          </option>
        ))}
      </select>
      <textarea
        className="lb-notas"
        placeholder="notas…"
        value={notas}
        disabled={busy}
        onChange={(e) => setNotas(e.target.value)}
        onBlur={() => void saveNotas()}
      />
      <div className="lb-card-actions">
        <button className="lb-link" onClick={() => onOpenLot(item.lote_id)}>
          ver no mapa
        </button>
        <button className="lb-link danger" onClick={() => void remove()} disabled={busy}>
          remover
        </button>
      </div>
    </div>
  )
}
