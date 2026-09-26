import type { Listing, OportunidadeTier } from '../api/types'
import type { CamposFicha } from './FichaCampos'

const nf0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 })
const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })

// Mesmos selos do card do BestPlaces (bestplaces-web/src/lib/deal.ts) — o anúncio fala a mesma
// língua nos dois apps.
export const TIER_INFO: Record<OportunidadeTier, { rotulo: string; classe: string }> = {
  rara: { rotulo: '🔥 Oportunidade rara', classe: 'tier-rara' },
  boa: { rotulo: 'Boa oportunidade', classe: 'tier-boa' },
  incerta: { rotulo: 'Pode valer a pena', classe: 'tier-incerta' },
  mercado: { rotulo: 'Preço de mercado', classe: 'tier-mercado' },
  acima: { rotulo: 'Acima da estimativa', classe: 'tier-acima' },
  suspeito: { rotulo: '⚠ Bom demais — verificar', classe: 'tier-suspeito' },
}

const METODO: Record<string, string> = {
  ponto_no_lote: 'pino do anúncio dentro do lote',
  ponto_proximo: 'pino na rua, lote vizinho com a mesma área',
  area_raio: 'endereço oculto: único lote do bairro com a área anunciada num raio de 300 m',
  manual: 'conferido manualmente',
}

function explicacao(l: Listing): string | null {
  if (!l.oportunidade_tier || l.preco_esperado == null) return null
  const faixa =
    l.preco_esperado_lo != null && l.preco_esperado_hi != null
      ? `${brl.format(l.preco_esperado_lo)} a ${brl.format(l.preco_esperado_hi)}`
      : brl.format(l.preco_esperado)
  const modelo =
    l.oportunidade_modelo === 'hedonico'
      ? 'modelo de preço de terreno (localização, mar, área)'
      : 'modelo de preço do BestPlaces (área, quartos, bairro, coordenada)'
  if (l.oportunidade_tier === 'suspeito')
    return `Preço muito fora da faixa esperada (${faixa}). Costuma ser erro de cadastro ou detalhe oculto — confirme antes.`
  const d = l.desconto_pct ?? 0
  const lado = d >= 0 ? `${nf0.format(d * 100)}% abaixo` : `${nf0.format(-d * 100)}% acima`
  const cautela =
    (l.confiabilidade ?? 0) < 0.25 ? ' Poucos comparáveis parecidos: leia como indício, não como laudo.' : ''
  return `Pedido ${lado} do esperado. Faixa típica: ${faixa} (${modelo}).${cautela}`
}

export function AnuncioCard({ l, campos }: { l: Listing; campos: CamposFicha }) {
  const tier = l.oportunidade_tier ? TIER_INFO[l.oportunidade_tier] : null
  const exp = explicacao(l)
  const comodos = [
    l.quartos != null && `${l.quartos} quarto${l.quartos === 1 ? '' : 's'}`,
    l.banheiros != null && `${l.banheiros} banheiro${l.banheiros === 1 ? '' : 's'}`,
    l.vagas != null && `${l.vagas} vaga${l.vagas === 1 ? '' : 's'}`,
  ].filter(Boolean)
  return (
    <section className="anuncio" aria-labelledby={`anuncio-${l.anuncio_id}`}>
      <div className="anuncio-h">
        <h3 id={`anuncio-${l.anuncio_id}`}>À venda · {l.tipo ?? 'anúncio'}</h3>
        {tier && campos.mostra('anuncio.oportunidade') && (
          <span className={`tier ${tier.classe}`}>{tier.rotulo}</span>
        )}
      </div>
      {campos.mostra('anuncio.foto') && l.imagem_url && (
        <img className="anuncio-foto" src={l.imagem_url} alt={l.titulo ?? 'Foto do anúncio'} loading="lazy" />
      )}
      {campos.mostra('anuncio.preco') && l.preco != null && (
        <div className="anuncio-preco">{brl.format(l.preco)}</div>
      )}
      {campos.mostra('anuncio.preco_m2') && l.preco_m2_terreno != null && (
        <div className="k">{brl.format(l.preco_m2_terreno)}/m² de terreno (área do lote)</div>
      )}
      {campos.mostra('anuncio.oportunidade') && exp && <p className="anuncio-exp">{exp}</p>}
      <dl className="anuncio-attrs">
        {campos.mostra('anuncio.area') && l.area_anunc_m2 != null && (
          <>
            <dt>Área anunciada</dt>
            <dd>
              {nf0.format(l.area_anunc_m2)} m²
              {l.area_terreno_m2 != null && l.area_terreno_m2 !== l.area_anunc_m2 && (
                <> · terreno {nf0.format(l.area_terreno_m2)} m²</>
              )}
            </dd>
          </>
        )}
        {campos.mostra('anuncio.comodos') && comodos.length > 0 && (
          <>
            <dt>Cômodos</dt>
            <dd>{comodos.join(' · ')}</dd>
          </>
        )}
        {campos.mostra('anuncio.custos') && (l.iptu != null || l.condominio != null) && (
          <>
            <dt>Custos</dt>
            <dd>
              {l.iptu != null && <>IPTU {brl.format(l.iptu)}</>}
              {l.iptu != null && l.condominio != null && ' · '}
              {l.condominio != null && <>condomínio {brl.format(l.condominio)}/mês</>}
            </dd>
          </>
        )}
        {campos.mostra('anuncio.anunciante') && l.anunciante_nome && (
          <>
            <dt>Anunciante</dt>
            <dd>
              {l.anunciante_nome}
              {l.anunciante_creci && <> · CRECI {l.anunciante_creci}</>}
            </dd>
          </>
        )}
        {campos.mostra('anuncio.portais') && (
          <>
            <dt>Coletado</dt>
            <dd>
              {(l.fontes?.length ? l.fontes : [l.fonte]).join(', ')}
              {l.dias_desde_coleta != null &&
                ` · ${l.dias_desde_coleta === 0 ? 'hoje' : `há ${l.dias_desde_coleta} dia${l.dias_desde_coleta === 1 ? '' : 's'}`}`}
            </dd>
          </>
        )}
        {campos.mostra('anuncio.casamento') && l.casamento_metodo && (
          <>
            <dt>Lote certo?</dt>
            <dd>
              {METODO[l.casamento_metodo] ?? l.casamento_metodo}
              {l.casamento_score != null && ` (confiança ${nf0.format(l.casamento_score * 100)}%)`}
            </dd>
          </>
        )}
      </dl>
      {l.url && (
        <a className="btn ghost small" href={l.url} target="_blank" rel="noopener noreferrer">
          Ver anúncio no portal ↗
        </a>
      )}
    </section>
  )
}
