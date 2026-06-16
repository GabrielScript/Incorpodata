import { useState } from 'react'
import type { ReactNode } from 'react'
import type { LotFicha } from '../api/types'
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
          <button className={tab === 'resumo' ? 'on' : ''} onClick={() => setTab('resumo')}>
            Resumo
          </button>
          <button className={tab === 'completo' ? 'on' : ''} onClick={() => setTab('completo')}>
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

function Resumo({ lot }: { lot: LotFicha }) {
  const v = lot.viability
  const proj = v?.area_projecao_max_m2
  return (
    <div className="resumo">
      <h2>{lot.logradouro ?? `Lote ${lot.id}`}</h2>
      <div className="sub">
        {lot.bairro ?? '—'} · {m2(lot.area_geom_m2)} · {v?.sigla ?? 's/ zona'}
      </div>

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
          <div className="k">À venda</div>
          <div className="big">{lot.listing?.preco != null ? brl.format(lot.listing.preco) : '—'}</div>
          <div className="k">{lot.listing ? lot.listing.fonte : 'sem anúncio'}</div>
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
      <div className="phase">▸ Melhor uso (fase 2) · ▸ Valor ótimo p/ pagar (fase 3)</div>
      <div className="actions">
        <button className="btn" disabled title="Fase 3">
          + landbank
        </button>
        <button className="btn ghost" disabled title="Fase 4">
          PDF
        </button>
      </div>
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

      <Section title="Mercado">
        <Row
          k="À venda"
          val={lot.listing?.preco != null ? `${brl.format(lot.listing.preco)} · ${lot.listing.fonte}` : '—'}
        />
        <Row term="R$/m² terreno" k="R$/m² terreno" val={lot.listing?.preco_m2 != null ? brl.format(lot.listing.preco_m2) : '—'} />
        <Row k="Melhor uso" val="▸ fase 2" />
        <Row k="Valor residual" val="▸ fase 3" />
      </Section>
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
