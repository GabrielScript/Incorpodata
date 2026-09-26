import { createContext, useContext, useState } from 'react'
import type { ReactNode } from 'react'
import type { LotFicha } from '../api/types'
import { AnuncioCard } from './AnuncioCard'
import { CamposPicker, useCamposFicha, type CampoFicha, type CamposFicha } from './FichaCampos'
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

// Campos visíveis da ficha (seletor "Personalizar ficha"), acessíveis a qualquer Row.
const CamposCtx = createContext<CamposFicha | null>(null)
const useCampos = () => useContext(CamposCtx)

export function LotFichaPanel({ lot, loading, error, onBack }: Props) {
  const [tab, setTab] = useState<'resumo' | 'completo'>('resumo')
  const campos = useCamposFicha()
  return (
    <CamposCtx.Provider value={campos}>
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
      <CamposPicker campos={campos} />
      {lot && (tab === 'resumo' ? <Resumo lot={lot} /> : <Completo lot={lot} />)}
    </div>
    </CamposCtx.Provider>
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
  const campos = useCampos()
  const ver = (c: CampoFicha) => campos?.mostra(c) ?? true

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

      {lot.listing && campos && <AnuncioCard l={lot.listing} campos={campos} />}

      {vgv && ver('estudo.vgv') && (
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

      {residual && ver('estudo.residual') && (
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
  const campos = useCampos()
  const ver = (c: CampoFicha) => campos?.mostra(c) ?? true
  return (
    <div className="completo">
      <h2>{lot.logradouro ?? `Lote ${lot.id}`}</h2>
      <div className="sub">
        {ver('terreno.inscricao') && <>{lot.inscricao ?? '—'} · </>}
        {lot.bairro ?? '—'} · {lot.tipo ?? '—'}
      </div>

      <Section title="Terreno">
        <Row c="terreno.area_cad" k="Área cadastral" val={lot.area_cad_m2 != null ? m2(lot.area_cad_m2) : '—'} />
        <Row c="terreno.area_geom" k="Área (geometria)" val={m2(lot.area_geom_m2)} />
        <Row c="terreno.quadra_lote" k="Quadra / Lote" val={`${lot.quadra ?? '—'} / ${lot.lote ?? '—'}`} />
      </Section>

      <Section title="Zoneamento (LUOS 166/2024)">
        <Row c="zona.zona" term="Zona" k="Zona" val={v?.sigla ? `${v.sigla}${v.nome_zona ? ` · ${v.nome_zona}` : ''}` : '—'} />
        <Row c="zona.altura" term="Altura" k="Altura" val={lot.restricao.altura_label} />
        <Row c="zona.orla" term="Faixa orla" k="Faixa orla" val={lot.restricao.faixa_orla ?? 'não'} />
        <Row c="zona.iphaep" term="IPHAEP" k="IPHAEP" val={lot.restricao.em_centro_historico ? 'sim' : 'não'} />
      </Section>

      <Section title="O que cabe">
        <Row c="zona.projecao" term="Projeção térreo" k="Projeção térreo (TO)" val={`${m2(v?.area_projecao_max_m2)} (${pct(v?.to_max_pct)})`} />
        <Row c="zona.permeavel" term="Permeável mín" k="Permeável mín (TAP)" val={`${m2(v?.area_permeavel_min_m2)} (${pct(v?.tap_min_pct)})`} />
        <Row c="zona.recuos" term="Recuo" k="Recuo frontal" val={v?.recuo_frontal_m != null ? `${v.recuo_frontal_m} m` : '—'} />
        <Row c="zona.recuos" term="Recuo" k="Recuo lateral" val={v?.recuo_lateral ?? '—'} />
        <Row c="zona.recuos" term="Recuo" k="Recuo fundo" val={v?.recuo_fundo ?? '—'} />
        <Row c="zona.usos" term="Usos" k="Usos" val={v?.usos_obs ?? '—'} />
      </Section>

      {lot.listing && <SecaoAnuncio lot={lot} />}

      {lot.vgv && ver('estudo.vgv') && (
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

      {lot.financiamento && ver('financ.simulacao') && <SecaoFinanciamento lot={lot} />}

      {lot.residual && ver('estudo.residual') && (
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
    <div className="section" role="group" aria-label={title}>
      <div className="section-h">{title}</div>
      {children}
    </div>
  )
}

function Row({ k, val, term, c }: { k: string; val: string; term?: string; c?: CampoFicha }) {
  const campos = useCampos()
  if (c && campos && !campos.mostra(c)) return null
  return (
    <div className="frow">
      <span className="fk">{term ? <Term k={term} label={k} /> : k}</span>
      <span className="fv">{val}</span>
    </div>
  )
}

function SecaoAnuncio({ lot }: { lot: LotFicha }) {
  const l = lot.listing
  if (!l) return null
  const brlOu = (v?: number | null) => (v == null ? '—' : brl.format(v))
  return (
    <Section title={`Anúncio à venda · ${l.tipo ?? ''}`}>
      <Row c="anuncio.preco" k="Preço pedido" val={brlOu(l.preco)} />
      <Row c="anuncio.preco_m2" k="R$/m² do terreno (área do lote)" val={brlOu(l.preco_m2_terreno)} />
      <Row c="anuncio.oportunidade" k="Preço esperado (faixa típica)" val={
        l.preco_esperado == null
          ? '—'
          : `${brl.format(l.preco_esperado)}${l.preco_esperado_lo != null && l.preco_esperado_hi != null ? ` (${brl.format(l.preco_esperado_lo)}–${brl.format(l.preco_esperado_hi)})` : ''}`
      } />
      <Row c="anuncio.oportunidade" k="Pedido × esperado" val={
        l.desconto_pct == null ? '—' : `${pct(Math.abs(l.desconto_pct) * 100)} ${l.desconto_pct >= 0 ? 'abaixo' : 'acima'}`
      } />
      <Row c="anuncio.area" k="Área anunciada" val={m2(l.area_anunc_m2)} />
      <Row c="anuncio.area" k="Área do terreno (anúncio)" val={m2(l.area_terreno_m2)} />
      {/* terreno: a API zera os cômodos -> as linhas somem em vez de "— / —" */}
      {(l.quartos != null || l.suites != null) && (
        <Row c="anuncio.comodos" k="Quartos / suítes" val={`${l.quartos ?? '—'} / ${l.suites ?? '—'}`} />
      )}
      {(l.banheiros != null || l.vagas != null) && (
        <Row c="anuncio.comodos" k="Banheiros / vagas" val={`${l.banheiros ?? '—'} / ${l.vagas ?? '—'}`} />
      )}
      <Row c="anuncio.custos" k="IPTU (anunciado)" val={brlOu(l.iptu)} />
      <Row c="anuncio.custos" k="Condomínio (mês)" val={brlOu(l.condominio)} />
      <Row c="anuncio.anunciante" k="Anunciante" val={l.anunciante_nome ?? '—'} />
      <Row c="anuncio.anunciante" k="CRECI" val={l.anunciante_creci ?? '—'} />
      <Row c="anuncio.portais" k="Portais" val={(l.fontes?.length ? l.fontes : [l.fonte]).join(', ')} />
      <Row c="anuncio.portais" k="Coletado em" val={l.coletado_em ? new Date(l.coletado_em).toLocaleDateString('pt-BR') : '—'} />
      <Row c="anuncio.casamento" k="Casamento com o lote" val={
        `${l.casamento_metodo ?? '—'}${l.casamento_score != null ? ` · ${pct(l.casamento_score * 100)}` : ''}${l.loc_aproximada ? ' · pino aproximado' : ''}`
      } />
    </Section>
  )
}

const NOME_CENARIO: Record<string, string> = {
  mercado: 'Taxa de mercado (SFI)',
  regulada: 'Taxa regulada (SFH/FGTS)',
}

function SecaoFinanciamento({ lot }: { lot: LotFicha }) {
  const f = lot.financiamento
  if (!f) return null
  return (
    <Section title="Financiamento do comprador (juros BCB)">
      <Row
        k="Unidade típica"
        val={`${m2(f.unidade_area_m2)} · ${brl.format(f.unidade_valor)} · entrada ${pct(f.entrada_pct * 100)} · ${f.prazo_meses / 12} anos`}
      />
      {f.cenarios.map((c) => (
        <div key={c.nome} className="financ-cenario">
          <div className="financ-h">
            {NOME_CENARIO[c.nome] ?? c.nome} · {c.taxa_aa_pct.toLocaleString('pt-BR')}% a.a.{' '}
            <span className="k">({c.fonte ?? 'BCB'}, {new Date(c.data_ref).toLocaleDateString('pt-BR', { month: 'short', year: 'numeric', timeZone: 'UTC' })})</span>
          </div>
          <Row k="Parcela SAC (1ª → última)" val={`${brl.format(c.parcela_sac_inicial)} → ${brl.format(c.parcela_sac_final)}`} />
          <Row k="Parcela Price (fixa)" val={brl.format(c.parcela_price)} />
          <Row k="Renda familiar mínima" val={`${brl.format(c.renda_minima)}/mês`} />
          <Row k="…se o juro subir 1 p.p." val={`${brl.format(c.renda_minima_mais_1pp)}/mês`} />
        </div>
      ))}
      <p className="nota">{f.premissas}</p>
    </Section>
  )
}
