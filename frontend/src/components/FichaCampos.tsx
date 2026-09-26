import { useCallback, useEffect, useId, useState } from 'react'

// Catálogo dos campos da ficha que o usuário pode ligar/desligar ("Personalizar ficha").
// Agrupado por assunto: terreno (cadastro/zoneamento) × anúncio (portal) × bairro × financiamento.
// A escolha fica no navegador (localStorage), como o landbank — sem login.
export const GRUPOS_CAMPOS = [
  {
    grupo: 'Terreno',
    campos: [
      ['terreno.area_cad', 'Área cadastral'],
      ['terreno.area_geom', 'Área (geometria)'],
      ['terreno.quadra_lote', 'Quadra / lote'],
      ['terreno.inscricao', 'Inscrição imobiliária'],
      ['terreno.marinha', 'Terreno de marinha'],
    ],
  },
  {
    grupo: 'Zoneamento e o que cabe',
    campos: [
      ['zona.zona', 'Zona (LUOS)'],
      ['zona.altura', 'Altura'],
      ['zona.orla', 'Faixa da orla'],
      ['zona.iphaep', 'Centro histórico (IPHAEP)'],
      ['zona.projecao', 'Projeção no térreo (TO)'],
      ['zona.permeavel', 'Permeável mínimo (TAP)'],
      ['zona.recuos', 'Recuos'],
      ['zona.usos', 'Usos permitidos'],
    ],
  },
  {
    grupo: 'Estudo de massa',
    campos: [
      ['estudo.vgv', 'VGV potencial'],
      ['estudo.residual', 'Valor residual (quanto pagar)'],
    ],
  },
  {
    grupo: 'Anúncio',
    campos: [
      ['anuncio.foto', 'Foto'],
      ['anuncio.preco', 'Preço pedido'],
      ['anuncio.preco_m2', 'R$/m² do terreno'],
      ['anuncio.oportunidade', 'Oportunidade (preço × esperado)'],
      ['anuncio.area', 'Áreas anunciadas'],
      ['anuncio.comodos', 'Quartos / banheiros / vagas'],
      ['anuncio.custos', 'IPTU e condomínio'],
      ['anuncio.anunciante', 'Anunciante e CRECI'],
      ['anuncio.portais', 'Portais e data da coleta'],
      ['anuncio.casamento', 'Confiança do casamento com o lote'],
    ],
  },
  {
    grupo: 'Bairro',
    campos: [
      ['bairro.valorizacao', 'Valorização e potencial'],
      ['bairro.incorporadoras', 'Incorporadoras ativas'],
    ],
  },
  {
    grupo: 'Financiamento',
    campos: [['financ.simulacao', 'Parcela e renda mínima (BCB)']],
  },
] as const

export type CampoFicha = (typeof GRUPOS_CAMPOS)[number]['campos'][number][0]

const KEY = 'incorpodata_ficha_ocultos'

function ler(): Set<string> {
  try {
    const v: unknown = JSON.parse(localStorage.getItem(KEY) ?? '[]')
    return new Set(Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [])
  } catch {
    return new Set() // storage bloqueado/corrompido → mostra tudo
  }
}

/** Campos visíveis da ficha. `mostra(c)` diz se o campo aparece; `alterna(c)` liga/desliga. */
export function useCamposFicha() {
  const [ocultos, setOcultos] = useState<Set<string>>(ler)

  // Outras abas/fichas abertas acompanham a escolha.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === KEY) setOcultos(ler())
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const gravar = useCallback((s: Set<string>) => {
    setOcultos(s)
    try {
      localStorage.setItem(KEY, JSON.stringify([...s]))
    } catch {
      /* modo anônimo: vale só nesta sessão */
    }
  }, [])

  const mostra = useCallback((c: CampoFicha) => !ocultos.has(c), [ocultos])
  const alterna = useCallback(
    (c: CampoFicha) => {
      const s = new Set(ocultos)
      if (s.has(c)) s.delete(c)
      else s.add(c)
      gravar(s)
    },
    [ocultos, gravar],
  )
  const todos = useCallback((ligar: boolean) => {
    gravar(ligar ? new Set() : new Set(GRUPOS_CAMPOS.flatMap((g) => g.campos.map(([c]) => c))))
  }, [gravar])

  return { mostra, alterna, todos }
}

export type CamposFicha = ReturnType<typeof useCamposFicha>

/** Botão "Personalizar ficha" + painel de checkboxes agrupados (fieldset/legend p/ leitor de tela). */
export function CamposPicker({ campos }: { campos: CamposFicha }) {
  const [aberto, setAberto] = useState(false)
  const painelId = useId()
  return (
    <div className="campos-picker">
      <button
        type="button"
        className="btn ghost small"
        aria-expanded={aberto}
        aria-controls={painelId}
        onClick={() => setAberto((a) => !a)}
      >
        ⚙ Personalizar ficha
      </button>
      <div id={painelId} className="campos-painel" hidden={!aberto}>
        <p className="campos-dica">Escolha o que aparece na ficha (fica salvo neste navegador).</p>
        {GRUPOS_CAMPOS.map((g) => (
          <fieldset key={g.grupo}>
            <legend>{g.grupo}</legend>
            {g.campos.map(([c, rotulo]) => (
              <label key={c} className="check">
                <input type="checkbox" checked={campos.mostra(c)} onChange={() => campos.alterna(c)} />
                {rotulo}
              </label>
            ))}
          </fieldset>
        ))}
        <div className="campos-acoes">
          <button type="button" className="btn ghost small" onClick={() => campos.todos(true)}>
            Mostrar tudo
          </button>
          <button type="button" className="btn ghost small" onClick={() => campos.todos(false)}>
            Ocultar tudo
          </button>
        </div>
      </div>
    </div>
  )
}
