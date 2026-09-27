import { useState } from 'react'
import type { ReactNode } from 'react'
import type { LotFicha } from '../api/types'
import { addLandbank, lotPdfUrl } from '../api/client'
import { GLOSSARY } from '../glossary'

const nf0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 })
const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
const m2 = (v?: number | null) => (v == null ? '—' : `${nf0.format(v)} m²`)
const pct = (v?: number | null) => (v == null ? '—' : `${nf0.format(v)}%`)

/** Termo técnico com explicação no hover (tooltip). `k` é a chave do glossário. */
function Term({ k, label }: { k: string; label?: string }) {
  const def = GLOSSARY[k]
  const text = label ?? k
  return def ? (
    <abbr className="term" title={def}>
      {text}
    </abbr>
  ) : (
    <>{text}</>
  )
}

interface Props {
  lot: LotFicha | null
  loading: boolean
  error: Error | null
  onBack: () => void
}

export function LotFichaPanel({ lot, loading, error, onBack }: Props) {
  const [tab, setTab] = useState<'resumo' | 'completo'>('resumo')
  return (
    <div className="ficha">
      <div className="ficha-top">
        <button className="back" onClick={onBack}>
          ← resultados
        </button>
        <div className="seg">
          <button
            className={tab === 'resumo' ? 'on' : ''}
            aria-pressed={tab === 'resumo'}
            onClick={() => setTab('resumo')}
          >
            Resumo
          </button>
          <button
            className={tab === 'completo' ? 'on' : ''}
            aria-pressed={tab === 'completo'}
            onClick={() => setTab('completo')}
          >
            Completo
          </button>
        </div>
      </div>
      {loading && <div className="state">Carregando ficha…</div>}
      {error && <div className="state error">Erro: {error.message}</div>}
      {lot && (tab === 'resumo' ? <Resumo lot={lot} /> : <Completo lot={lot} />)}
    </div>
  )
}

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

function Resumo({ lot }: { lot: LotFicha }) {
  const v = lot.viability
  const proj = v?.area_projecao_max_m2
  const vgv = lot.vgv
  const residual = lot.residual
  const [save, setSave] = useState<SaveState>('idle')
  const [saveMsg, setSaveMsg] = useState<string | null>(null)

  async function onSaveLandbank() {
    setSave('saving')
    setSaveMsg(null)
    try {
      await addLandbank(lot)
      setSave('saved')
    } catch (e) {
      setSave('error')
      setSaveMsg((e as Error).message)
    }
  }

  return (
    <div className="resumo">
      <h2>{lot.logradouro ?? `Lote ${lot.id}`}</h2>
      <div className="sub">
        {lot.bairro ?? '—'} · {m2(lot.area_geom_m2)} · {v?.sigla ?? 's/ zona'}
      </div>

      {lot.centroid && (
        <a
          className="streetview-link"
          href={`https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lot.centroid[1]},${lot.centroid[0]}`}
          target="_blank"
          rel="noopener noreferrer"
          title="Abre o Google Street View na localização do lote (nova aba)"
        >
          📍 Ver na rua (Street View)
        </a>
      )}

      {lot.geometria_suspeita && (
        <div className="aviso-suspeita" role="alert">
          ⚠ {lot.geometria_aviso ?? 'Área acima do padrão de lote urbano (gleba/ZEPA). VGV de prédio único não se aplica.'}
        </div>
      )}

      {vgv && (
        <div className="vgv">
          <div className="vgv-h">
            <Term k="VGV" label="VGV potencial" />
            <span className="tag prelim" title="Estimativa preliminar de estudo de massa — não substitui projeto/avaliação">
              preliminar
            </span>
          </div>
          <div className="vgv-nums">
            <div>
              <div className="vgv-big">{brl.format(vgv.vgv_por_pavimento)}</div>
              <div className="k">
                por pavimento
                {vgv.vgv_por_pavimento_min != null && vgv.vgv_por_pavimento_max != null && (
                  <>
                    {' '}
                    · faixa {brl.format(vgv.vgv_por_pavimento_min)}–{brl.format(vgv.vgv_por_pavimento_max)}
                  </>
                )}
              </div>
            </div>
            <div>
              <div className="vgv-big">{brl.format(vgv.vgv_total)}</div>
              <div className="k">total · {vgv.pavimentos} pav (premissa)</div>
            </div>
          </div>
          <div className="vgv-foot">
            {brl.format(vgv.preco_m2_venda)}/m²
            {vgv.preco_m2_q1 != null && vgv.preco_m2_q3 != null && (
              <> (Q1–Q3 {brl.format(vgv.preco_m2_q1)}–{brl.format(vgv.preco_m2_q3)})</>
            )}{' '}
            · n={nf0.format(vgv.n_comps)} · {vgv.fonte_preco === 'raio' ? 'raio do lote' : 'bairro'} · efic{' '}
            {pct(vgv.eficiencia * 100)}
          </div>
        </div>
      )}

      {residual && (
        <div className="residual">
          <div className="residual-h">
            <Term k="Valor residual" label="Quanto pagar" />
            <span
              className="prelim"
              title="Máximo a pagar pelo terreno p/ atingir a margem-alvo — método involutivo, preliminar"
            >
              involutivo
            </span>
          </div>
          {residual.residual_total > 0 ? (
            <>
              <div className="residual-big">até {brl.format(residual.residual_total)}</div>
              <div className="k">
                máx p/ margem de {pct(residual.margem_alvo * 100)}
                {residual.terreno_pct_vgv != null && <> · {pct(residual.terreno_pct_vgv * 100)} do VGV</>}
                {residual.residual_total_min != null && residual.residual_total_max != null && (
                  <>
                    {' '}
                    · faixa {brl.format(residual.residual_total_min)}–{brl.format(residual.residual_total_max)}
                  </>
                )}
              </div>
            </>
          ) : (
            <div className="residual-inviavel">Inviável às premissas — custo + margem superam o VGV</div>
          )}
          {residual.gap_pct != null && (
            <div className={`barganha ${residual.cabe_no_bolso ? 'ok' : 'caro'}`}>
              {residual.cabe_no_bolso ? '✓ cabe no bolso' : '✗ caro demais'}
              {residual.preco_pedido != null && <> · pedido {brl.format(residual.preco_pedido)}</>} ·{' '}
              {pct(Math.abs(residual.gap_pct) * 100)} {residual.cabe_no_bolso ? 'de folga' : 'acima do máximo'}
            </div>
          )}
        </div>
      )}

      <div className="cards">
        <div className="card">
          <div className="k">
            <Term k="Projeção térreo" label="Cabe no térreo" />
          </div>
          <div className="big">{m2(proj)}</div>
          <div className="k">
            <Term k="TO" label="Taxa de ocupação" /> {pct(v?.to_max_pct)}
          </div>
        </div>
        <div className="card">
          <div className="k">
            <Term k="TAP" label="Área permeável mín." />
          </div>
          <div className="big">{m2(v?.area_permeavel_min_m2)}</div>
          <div className="k">
            <Term k="TAP" label="Taxa permeável" /> {pct(v?.tap_min_pct)}
          </div>
        </div>
      </div>

      <div className="altura">
        <span className="altura-k">
          <Term k="Altura" label="Quanto pode subir" />
        </span>
        <strong>{lot.restricao.altura_label}</strong>
      </div>

      <p className="plain">
        Em miúdos: a construção pode ocupar até <strong>{m2(proj)}</strong> no térreo, e o quanto
        sobe depende da altura acima e dos recuos.
      </p>

      {v?.usos_obs && (
        <div className="usos">
          <strong>
            <Term k="Usos" label="O que pode funcionar ali" />:
          </strong>{' '}
          {v.usos_obs}
        </div>
      )}
      <div className="actions">
        <button className="btn" onClick={onSaveLandbank} disabled={save === 'saving' || save === 'saved'}>
          {save === 'saved' ? '✓ no landbank' : save === 'saving' ? 'salvando…' : '+ landbank'}
        </button>
        <a className="btn ghost" href={lotPdfUrl(lot.id)} target="_blank" rel="noreferrer">
          PDF
        </a>
      </div>
      {save === 'error' && <div className="save-err">Não salvou: {saveMsg}</div>}
    </div>
  )
}

function Completo({ lot }: { lot: LotFicha }) {
  const v = lot.viability
  return (
    <div className="completo">
      <h2>{lot.logradouro ?? `Lote ${lot.id}`}</h2>
      <div className="sub">
        {lot.inscricao ?? '—'} · {lot.bairro ?? '—'} · {lot.tipo ?? '—'}
      </div>

      <Section title="Terreno">
        <Row k="Área cadastral" val={lot.area_cad_m2 != null ? m2(lot.area_cad_m2) : '—'} />
        <Row k="Área (geometria)" val={m2(lot.area_geom_m2)} />
        <Row k="Quadra / Lote" val={`${lot.quadra ?? '—'} / ${lot.lote ?? '—'}`} />
      </Section>

      <Section title="Zoneamento (LUOS 166/2024)">
        <Row term="Zona" k="Zona" val={v?.sigla ? `${v.sigla}${v.nome_zona ? ` · ${v.nome_zona}` : ''}` : '—'} />
        <Row term="Altura" k="Altura" val={lot.restricao.altura_label} />
        <Row term="Faixa orla" k="Faixa orla" val={lot.restricao.faixa_orla ?? 'não'} />
        <Row term="IPHAEP" k="IPHAEP" val={lot.restricao.em_centro_historico ? 'sim' : 'não'} />
      </Section>

      <Section title="O que cabe">
        <Row term="Projeção térreo" k="Projeção térreo (TO)" val={`${m2(v?.area_projecao_max_m2)} (${pct(v?.to_max_pct)})`} />
        <Row term="Permeável mín" k="Permeável mín (TAP)" val={`${m2(v?.area_permeavel_min_m2)} (${pct(v?.tap_min_pct)})`} />
        <Row term="Recuo" k="Recuo frontal" val={v?.recuo_frontal_m != null ? `${v.recuo_frontal_m} m` : '—'} />
        <Row term="Recuo" k="Recuo lateral" val={v?.recuo_lateral ?? '—'} />
        <Row term="Recuo" k="Recuo fundo" val={v?.recuo_fundo ?? '—'} />
        <Row term="Usos" k="Usos" val={v?.usos_obs ?? '—'} />
      </Section>

      {lot.vgv && (
        <Section title="VGV potencial (estudo de massa · preliminar)">
          <Row term="VGV" k="VGV por pavimento" val={brl.format(lot.vgv.vgv_por_pavimento)} />
          {lot.vgv.vgv_por_pavimento_min != null && lot.vgv.vgv_por_pavimento_max != null && (
            <Row
              k="Faixa por pavimento (Q1–Q3)"
              val={`${brl.format(lot.vgv.vgv_por_pavimento_min)} – ${brl.format(lot.vgv.vgv_por_pavimento_max)}`}
            />
          )}
          <Row k={`VGV total (${lot.vgv.pavimentos} pav, premissa)`} val={brl.format(lot.vgv.vgv_total)} />
          <Row
            k={`R$/m² venda (${lot.vgv.fonte_preco === 'raio' ? 'raio do lote' : 'bairro'})`}
            val={
              lot.vgv.preco_m2_q1 != null && lot.vgv.preco_m2_q3 != null
                ? `${brl.format(lot.vgv.preco_m2_venda)} · Q1–Q3 ${brl.format(lot.vgv.preco_m2_q1)}–${brl.format(lot.vgv.preco_m2_q3)} · n=${lot.vgv.n_comps}`
                : `${brl.format(lot.vgv.preco_m2_venda)} · n=${lot.vgv.n_comps}`
            }
          />
          <Row k="Área privativa total" val={m2(lot.vgv.area_privativa_total_m2)} />
          <Row k="Eficiência" val={pct(lot.vgv.eficiencia * 100)} />
        </Section>
      )}

      {lot.residual && (
        <Section title="Valor residual — quanto pagar (involutivo · preliminar)">
          <Row
            term="Valor residual"
            k="Máximo a pagar (total)"
            val={lot.residual.residual_total > 0 ? brl.format(lot.residual.residual_total) : 'inviável às premissas'}
          />
          {lot.residual.residual_total_min != null && lot.residual.residual_total_max != null && (
            <Row
              k="Faixa (Q1–Q3)"
              val={`${brl.format(lot.residual.residual_total_min)} – ${brl.format(lot.residual.residual_total_max)}`}
            />
          )}
          <Row k="Máx por pavimento" val={brl.format(lot.residual.residual_por_pavimento)} />
          {lot.residual.terreno_pct_vgv != null && (
            <Row k="Terreno / VGV" val={pct(lot.residual.terreno_pct_vgv * 100)} />
          )}
          <Row k="Margem-alvo" val={pct(lot.residual.margem_alvo * 100)} />
          <Row k="Custo de obra (premissa)" val={`${brl.format(lot.residual.custo_obra_m2)}/m²`} />
          {lot.residual.gap_pct != null && (
            <Row
              k="Barganha vs pedido"
              val={`${lot.residual.cabe_no_bolso ? 'cabe' : 'caro'} · ${pct(Math.abs(lot.residual.gap_pct) * 100)} ${
                lot.residual.cabe_no_bolso ? 'de folga' : 'acima'
              }`}
            />
          )}
        </Section>
      )}

    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="section">
      <div className="section-h">{title}</div>
      {children}
    </div>
  )
}

function Row({ k, val, term }: { k: string; val: string; term?: string }) {
  return (
    <div className="frow">
      <span className="fk">{term ? <Term k={term} label={k} /> : k}</span>
      <span className="fv">{val}</span>
    </div>
  )
}
