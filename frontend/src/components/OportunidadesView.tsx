import { useAsync } from '../hooks/useApi'
import { listOportunidades } from '../api/client'
import { ScoreBars } from './LotFichaPanel'
import type { Oportunidade } from '../api/types'

const nf0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 })
const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
const pct = (v?: number | null) => (v == null ? '—' : `${nf0.format(v)}%`)

interface Props {
  bairro: string
  authed: boolean
  onRequireAuth: () => void
  onOpenLot: (id: number) => void
}

/** Ranking das melhores oportunidades do recorte por IncorpoScore (feature paga). */
export function OportunidadesView({ bairro, authed, onRequireAuth, onOpenLot }: Props) {
  const ops = useAsync(
    () => (authed ? listOportunidades(bairro, 20) : Promise.resolve<Oportunidade[]>([])),
    [bairro, authed],
  )

  if (!authed) {
    return (
      <div className="oportunidades">
        <div className="state">
          O ranking de oportunidades é uma feature dos planos pagos.{' '}
          <button className="linkbtn" onClick={onRequireAuth}>
            Entrar
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="oportunidades">
      <div className="op-head">
        <h2>Melhores oportunidades {bairro ? `· ${bairro}` : '· todos os bairros'}</h2>
        <span className="op-sub">ordenado por IncorpoScore · {ops.data?.length ?? 0} lotes</span>
      </div>
      {ops.loading && <div className="state">Avaliando lotes…</div>}
      {ops.error && <div className="state error">Erro: {ops.error.message}</div>}
      {ops.data && ops.data.length === 0 && !ops.loading && !ops.error && (
        <div className="state">Nenhuma oportunidade ranqueável no recorte.</div>
      )}
      <ol className="op-list">
        {ops.data?.map((o, i) => (
          <li key={o.lot_id} className="op-card" onClick={() => onOpenLot(o.lot_id)}>
            <div className="op-rank">{i + 1}</div>
            <div className="op-main">
              <div className="op-top">
                <strong>{o.logradouro ?? `Lote ${o.lot_id}`}</strong>
                <span className="op-score">
                  {nf0.format(o.score.total)}
                  <small>/100</small>
                </span>
              </div>
              <div className="op-meta">
                {o.bairro ?? '—'} · {o.area_m2 != null ? `${nf0.format(o.area_m2)} m²` : '—'} · pagar até{' '}
                <strong>{o.residual_total > 0 ? brl.format(o.residual_total) : 'inviável'}</strong>
                {o.terreno_pct_vgv != null && o.residual_total > 0 && <> ({pct(o.terreno_pct_vgv * 100)} do VGV)</>}
                {o.gap_pct != null && (
                  <span className={`op-gap ${o.cabe_no_bolso ? 'ok' : 'caro'}`}>
                    {' '}
                    · {o.cabe_no_bolso ? '✓ cabe' : '✗ caro'} {pct(Math.abs(o.gap_pct) * 100)}
                  </span>
                )}
              </div>
              <ScoreBars score={o.score} />
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
