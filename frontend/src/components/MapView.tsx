import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import type { FeatureCollection, Geometry } from 'geojson'
import type {
  ExpressionSpecification,
  GeoJSONSource,
  Map as MLMap,
  StyleSpecification,
} from 'maplibre-gl'

// Dois basemaps SEM chave, alternáveis: Esri World Street Map (ruas) e Esri World Imagery
// (satélite). O satélite mostra o terreno real visto de cima, com o polígono do lote por cima —
// dá pra ver se está vago, o que há nele e a vizinhança. Satélite começa oculto.
// CARTO Positron saiu em 09/2026: basemaps.cartocdn.com passou a exigir chave e devolve HTTP 200
// com um PNG "API KEY REQUIRED" em todo tile (não dá erro — só pinta o aviso no mapa).
const STYLE: StyleSpecification = {
  version: 8,
  sources: {
    ruas: {
      type: 'raster',
      tiles: [
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
      ],
      tileSize: 256,
      maxzoom: 19, // acima disso o MapLibre amplia o z19 em vez de pedir tile inexistente
      attribution: '© Esri, HERE, Garmin, © OpenStreetMap',
    },
    esri: {
      type: 'raster',
      tiles: [
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      ],
      tileSize: 256,
      attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
    },
  },
  layers: [
    { id: 'ruas', type: 'raster', source: 'ruas' },
    { id: 'esri', type: 'raster', source: 'esri', layout: { visibility: 'none' } },
  ],
}

// Paint do lote, reusado no addLayer e no toggle (fonte única — não duplicar expressão).
// No mapa: cheio e colorido (legibilidade). No satélite: quase só contorno branco, pra a
// imagem do terreno aparecer por baixo do polígono.
const FILL_MAP: ExpressionSpecification = [
  'case',
  ['boolean', ['feature-state', 'selected'], false],
  0.6,
  0.22,
]
const FILL_SAT: ExpressionSpecification = [
  'case',
  ['boolean', ['feature-state', 'selected'], false],
  0.18,
  0,
]
const LINE_COLOR_MAP: ExpressionSpecification = [
  'case',
  ['boolean', ['feature-state', 'selected'], false],
  '#0b3d39',
  '#516068',
]
const LINE_WIDTH_MAP: ExpressionSpecification = [
  'case',
  ['boolean', ['feature-state', 'selected'], false],
  2.5,
  0.5,
]
const LINE_WIDTH_SAT: ExpressionSpecification = [
  'case',
  ['boolean', ['feature-state', 'selected'], false],
  3,
  1.2,
]

const BANCARIOS: [number, number] = [-34.834, -7.142] // [lng, lat]
const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

interface Props {
  data: FeatureCollection | null
  selectedId: number | null
  /** Centroide [lng, lat] do lote selecionado (da ficha): localiza o lote quando o polígono
   *  dele não está no recorte carregado (outro bairro/filtro). */
  selectedCenter: [number, number] | null
  onSelect: (id: number) => void
}

export function MapView({ data, selectedId, selectedCenter, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MLMap | null>(null)
  const readyRef = useRef(false)
  const selRef = useRef<number | null>(null) // id com feature-state 'selected' aplicado
  const pinRef = useRef<maplibregl.Marker | null>(null)
  const framedRef = useRef(false) // câmera já enquadrou algo nesta montagem do mapa
  // Últimas props, p/ os handlers do mapa (criados uma vez) não lerem valor velho.
  const onSelectRef = useRef(onSelect)
  const dataRef = useRef(data)
  const selIdRef = useRef(selectedId)
  const centerRef = useRef(selectedCenter)
  const [satellite, setSatellite] = useState(false)
  useEffect(() => {
    onSelectRef.current = onSelect
    dataRef.current = data
    selIdRef.current = selectedId
    centerRef.current = selectedCenter
  })

  // Destaque do lote selecionado (feature-state; sobrevive a setData).
  function paintSelected(m: MLMap) {
    if (selRef.current != null) m.removeFeatureState({ source: 'lots', id: selRef.current })
    if (selIdRef.current != null) {
      m.setFeatureState({ source: 'lots', id: selIdRef.current }, { selected: true })
    }
    selRef.current = selIdRef.current
  }

  // Localiza o lote selecionado: câmera no polígono dele (se está no recorte carregado) ou no
  // centroide da ficha — aí com pino, porque lote fora do recorte não tem polígono no mapa.
  // Só move a câmera se o lote não estiver bem à vista: clicar no mapa não dá pulo.
  function locateSelected(m: MLMap, move = true) {
    const id = selIdRef.current
    const center = centerRef.current
    const poly = id != null ? lotBounds(dataRef.current, id) : null
    const pin = id != null && !poly ? center : null
    if (pin) {
      pinRef.current = (pinRef.current ?? new maplibregl.Marker({ color: '#0b3d39' })).setLngLat(pin).addTo(m)
    } else {
      pinRef.current?.remove()
      pinRef.current = null
    }
    const alvo = poly ?? (pin ? new maplibregl.LngLatBounds(pin, pin) : null)
    if (!alvo || !move) return
    framedRef.current = true
    if (!wellInView(m, alvo)) {
      m.fitBounds(alvo, { padding: 80, maxZoom: poly ? 18 : 17, duration: prefersReducedMotion() ? 0 : 600 })
    }
  }

  // init (uma vez)
  useEffect(() => {
    if (!containerRef.current) return
    const m = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE,
      center: BANCARIOS,
      zoom: 14,
      attributionControl: { compact: true },
    })
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left')

    m.on('load', () => {
      m.addSource('lots', { type: 'geojson', data: EMPTY })
      m.addLayer({
        id: 'lots-fill',
        type: 'fill',
        source: 'lots',
        paint: {
          'fill-color': '#7c878d',
          'fill-opacity': FILL_MAP,
        },
      })
      m.addLayer({
        id: 'lots-line',
        type: 'line',
        source: 'lots',
        paint: {
          'line-color': LINE_COLOR_MAP,
          'line-width': LINE_WIDTH_MAP,
        },
      })
      readyRef.current = true
      const src = m.getSource('lots') as GeoJSONSource | undefined
      const data = dataRef.current
      if (src && data) src.setData(data)
      paintSelected(m)
      // Voltando pra aba com um lote aberto (vindo de Oportunidades/Landbank): vai até ele.
      if (selIdRef.current != null) locateSelected(m)
      else if (data) {
        fitToData(m, data)
        framedRef.current = true
      }
    })

    m.on('click', 'lots-fill', (e) => {
      const f = e.features?.[0]
      if (!f) return
      const id = Number(f.id ?? (f.properties as { id?: number } | null)?.id)
      if (!Number.isNaN(id)) onSelectRef.current(id)
    })
    m.on('mouseenter', 'lots-fill', () => {
      m.getCanvas().style.cursor = 'pointer'
    })
    m.on('mouseleave', 'lots-fill', () => {
      m.getCanvas().style.cursor = ''
    })

    mapRef.current = m
    return () => {
      m.remove()
      mapRef.current = null
      readyRef.current = false
      pinRef.current = null
      framedRef.current = false
    }
  }, [])

  // dados mudaram (filtro): enquadra o recorte novo — a menos que o lote aberto esteja nele
  // ou que seja a 1ª carga depois de chegar com um lote aberto; aí fica/vai no lote.
  useEffect(() => {
    const m = mapRef.current
    if (!m || !readyRef.current) return
    const src = m.getSource('lots') as GeoJSONSource | undefined
    if (!src || !data) return
    src.setData(data)
    const sel = selIdRef.current
    if (sel != null && (!framedRef.current || lotBounds(data, sel))) {
      locateSelected(m)
    } else {
      fitToData(m, data)
      framedRef.current = true
      locateSelected(m, false) // só acerta o pino (lote aberto que saiu do recorte)
    }
  }, [data])

  // seleção mudou (clique no mapa/lista, ou lote aberto de outra aba)
  useEffect(() => {
    const m = mapRef.current
    if (!m || !readyRef.current) return
    paintSelected(m)
    locateSelected(m)
  }, [selectedId])

  // ficha chegou com o centroide: localiza o lote que não tem polígono no recorte
  useEffect(() => {
    const m = mapRef.current
    if (!m || !readyRef.current || selectedCenter == null) return
    locateSelected(m)
  }, [selectedCenter])

  // basemap satélite on/off + legibilidade do polígono sobre a imagem
  useEffect(() => {
    const m = mapRef.current
    if (!m || !readyRef.current) return
    m.setLayoutProperty('esri', 'visibility', satellite ? 'visible' : 'none')
    m.setPaintProperty('lots-fill', 'fill-opacity', satellite ? FILL_SAT : FILL_MAP)
    m.setPaintProperty('lots-line', 'line-color', satellite ? '#ffffff' : LINE_COLOR_MAP)
    m.setPaintProperty('lots-line', 'line-width', satellite ? LINE_WIDTH_SAT : LINE_WIDTH_MAP)
  }, [satellite])

  return (
    <div className="map-wrap">
      <div ref={containerRef} className="map" />
      <div className="basemap-toggle" role="group" aria-label="Tipo de mapa">
        <button type="button" className={satellite ? '' : 'on'} onClick={() => setSatellite(false)}>
          Mapa
        </button>
        <button type="button" className={satellite ? 'on' : ''} onClick={() => setSatellite(true)}>
          Satélite
        </button>
      </div>
      <div className="legend">
        <span>
          <i className="sw vago" /> Vago
        </span>
      </div>
    </div>
  )
}

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true

function fitToData(m: MLMap, fc: FeatureCollection) {
  const b = new maplibregl.LngLatBounds()
  let any = false
  for (const f of fc.features) {
    if (extend(b, f.geometry)) any = true
  }
  if (any && !b.isEmpty()) {
    m.fitBounds(b, { padding: 40, maxZoom: 17, duration: prefersReducedMotion() ? 0 : 600 })
  }
}

/** Caixa do polígono do lote `id` no recorte carregado; null se ele não está no recorte. */
function lotBounds(fc: FeatureCollection | null, id: number): maplibregl.LngLatBounds | null {
  const f = fc?.features.find((x) => Number(x.id ?? (x.properties as { id?: number } | null)?.id) === id)
  if (!f) return null
  const b = new maplibregl.LngLatBounds()
  return extend(b, f.geometry) && !b.isEmpty() ? b : null
}

/** Lote já bem à vista: inteiro na tela e com zoom de enxergar lote (≥ 16). */
function wellInView(m: MLMap, b: maplibregl.LngLatBounds): boolean {
  const tela = m.getBounds()
  return m.getZoom() >= 16 && tela.contains(b.getSouthWest()) && tela.contains(b.getNorthEast())
}

function extend(b: maplibregl.LngLatBounds, g: Geometry | null): boolean {
  if (!g) return false
  if (g.type === 'Polygon') {
    for (const ring of g.coordinates) for (const c of ring) b.extend(c as [number, number])
    return true
  }
  if (g.type === 'MultiPolygon') {
    for (const poly of g.coordinates) for (const ring of poly) for (const c of ring) b.extend(c as [number, number])
    return true
  }
  return false
}
