import { useAsync } from '../hooks/useApi'
import { listOportunidades } from '../api/client'
import type { Oportunidade } from '../api/types'

const nf0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 })
const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
const pct = (v?: number | null) => (v == null ? '—' : `${nf0.format(v)}%`)

interface Props {
  bairro: string
  onOpenLot: (id: number) => void
}

/** Ranking das melhores oportunidades do recorte por valor residual. */
export function OportunidadesView({ bairro, onOpenLot }: Props) {
  // App aberto, sem login. Se PLANS_ENFORCED for ligado na API ela responde 402 — aí o
  // ranking fica indisponível até o login voltar ao frontend.
  const ops = useAsync<Oportunidade[]>(() => listOportunidades(bairro, 20), [bairro])
  const bloqueado = ops.error != null && /pago|plano|402/i.test(ops.error.message)

  if (bloqueado) {
    return (
      <div className="oportunidades">
        <div className="state">O ranking de oportunidades é uma feature dos planos pagos.</div>
      </div>
    )
  }

  return (
    <div className="oportunidades">
      <div className="op-head">
        <h2>Melhores oportunidades {bairro ? `· ${bairro}` : '· todos os bairros'}</h2>
        <span className="op-sub">ordenado por valor residual (quanto vale pagar) · {ops.data?.length ?? 0} lotes</span>
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
                <span className={`op-residual${o.residual_total > 0 ? '' : ' inviavel'}`}>
                  {o.residual_total > 0 ? brl.format(o.residual_total) : 'inviável'}
                </span>
              </div>
              <div className="op-meta">
                {o.bairro ?? '—'} · {o.area_m2 != null ? `${nf0.format(o.area_m2)} m²` : '—'} · VGV{' '}
                <strong>{brl.format(o.vgv_total)}</strong>
                {o.terreno_pct_vgv != null && o.residual_total > 0 && (
                  <> · terreno {pct(o.terreno_pct_vgv * 100)} do VGV</>
                )}
                {o.gap_pct != null && (
                  <span className={`op-gap ${o.cabe_no_bolso ? 'ok' : 'caro'}`}>
                    {' '}
                    · {o.cabe_no_bolso ? '✓ cabe' : '✗ caro'} {pct(Math.abs(o.gap_pct) * 100)}
                  </span>
                )}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
