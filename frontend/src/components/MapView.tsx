import { useEffect, useMemo, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import type { FeatureCollection, Geometry } from 'geojson'
import type {
  ExpressionSpecification,
  GeoJSONSource,
  Map as MLMap,
  StyleSpecification,
  VectorTileSource,
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
      // Em JP o World_Imagery tem tile real até z19; de z20 pra cima devolve HTTP 200 com o
      // placeholder cinza "Map data not yet available" (mapa todo cinza no zoom alto).
      maxzoom: 19,
      attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
    },
  },
  layers: [
    { id: 'ruas', type: 'raster', source: 'ruas' },
    { id: 'esri', type: 'raster', source: 'esri', layout: { visibility: 'none' } },
  ],
}

// Cor do lote: vago (o alvo) mais escuro que construído — sem "Só vagos", os tiles trazem a
// cidade inteira e os dois tipos se misturam no mapa.
const VAGO: ExpressionSpecification = ['==', ['get', 'tipo'], 'TERRITORIAL']
const COR_LOTE = {
  vago: '#7c878d',
  construido: '#b7bec2',
} as const
const FILL_COLOR: ExpressionSpecification = ['case', VAGO, COR_LOTE.vago, COR_LOTE.construido]

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

// Duas fontes de polígono de lote, com as mesmas camadas: abaixo do z13, o GeoJSON da lista
// (como antes); do z13 pra cima, os tiles vetoriais da API — a cidade inteira, sem o teto de
// lotes da lista. Um tile z12 teria ~110 mil lotes (1,3 MB), daí o corte. Zooms iguais aos
// TILE_MIN_ZOOM/TILE_MAX_ZOOM de src/api/lots.py; acima do z16 o MapLibre amplia o z16.
const TILE_MIN_ZOOM = 13
const TILE_MAX_ZOOM = 16
interface FonteLote {
  source: string
  sourceLayer?: string
  zoom: { minzoom?: number; maxzoom?: number }
}
const FONTE_LISTA: FonteLote = { source: 'lots', zoom: { maxzoom: TILE_MIN_ZOOM } }
const FONTE_TILES: FonteLote = { source: 'lots-tiles', sourceLayer: 'lotes', zoom: { minzoom: TILE_MIN_ZOOM } }
const FONTES = [FONTE_LISTA, FONTE_TILES]

const BANCARIOS: [number, number] = [-34.834, -7.142] // [lng, lat]
const MAX_ZOOM = 20
const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

interface Props {
  data: FeatureCollection | null
  /** URL-modelo ({z}/{x}/{y}) dos tiles vetoriais com o mesmo recorte de `data`. */
  tilesUrl: string
  selectedId: number | null
  /** Centroide [lng, lat] do lote selecionado (da ficha): localiza o lote quando o polígono
   *  dele não está no recorte carregado (outro bairro/filtro). */
  selectedCenter: [number, number] | null
  onSelect: (id: number) => void
}

export function MapView({ data, tilesUrl, selectedId, selectedCenter, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MLMap | null>(null)
  const readyRef = useRef(false)
  const selRef = useRef<number | null>(null) // id com feature-state 'selected' aplicado
  const pinRef = useRef<maplibregl.Marker | null>(null)
  const framedRef = useRef(false) // câmera já enquadrou algo nesta montagem do mapa
  // Últimas props, p/ os handlers do mapa (criados uma vez) não lerem valor velho.
  const onSelectRef = useRef(onSelect)
  const dataRef = useRef(data)
  const tilesUrlRef = useRef(tilesUrl)
  const selIdRef = useRef(selectedId)
  const centerRef = useRef(selectedCenter)
  const [satellite, setSatellite] = useState(false)
  // Legenda só com o que existe no recorte (fixa em "Vago" mentia com construídos na tela).
  const legenda = useMemo(() => {
    const l = { vago: false, construido: false }
    for (const f of data?.features ?? []) {
      if ((f.properties as { tipo?: string } | null)?.tipo === 'TERRITORIAL') l.vago = true
      else l.construido = true
    }
    return l
  }, [data])
  useEffect(() => {
    onSelectRef.current = onSelect
    dataRef.current = data
    tilesUrlRef.current = tilesUrl
    selIdRef.current = selectedId
    centerRef.current = selectedCenter
  })

  // Destaque do lote selecionado nas duas fontes (feature-state; sobrevive a setData/setTiles).
  function paintSelected(m: MLMap) {
    for (const { source, sourceLayer } of FONTES) {
      if (selRef.current != null) m.removeFeatureState({ source, sourceLayer, id: selRef.current })
      if (selIdRef.current != null) {
        m.setFeatureState({ source, sourceLayer, id: selIdRef.current }, { selected: true })
      }
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
      // Teto de zoom: 1 nível acima do último tile real (z19) — ampliado, sem virar cinza.
      maxZoom: MAX_ZOOM,
      attributionControl: { compact: true },
    })
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left')

    m.on('load', () => {
      m.addSource(FONTE_LISTA.source, { type: 'geojson', data: EMPTY })
      m.addSource(FONTE_TILES.source, {
        type: 'vector',
        tiles: [tilesUrlRef.current],
        minzoom: TILE_MIN_ZOOM,
        maxzoom: TILE_MAX_ZOOM,
      })
      for (const f of FONTES) addLotLayers(m, f)
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

    for (const { source } of FONTES) {
      m.on('click', `${source}-fill`, (e) => {
        const f = e.features?.[0]
        if (!f) return
        const id = Number(f.id ?? (f.properties as { id?: number } | null)?.id)
        if (!Number.isNaN(id)) onSelectRef.current(id)
      })
      m.on('mouseenter', `${source}-fill`, () => {
        m.getCanvas().style.cursor = 'pointer'
      })
      m.on('mouseleave', `${source}-fill`, () => {
        m.getCanvas().style.cursor = ''
      })
    }

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

  // filtro mudou: tiles do recorte novo (a câmera fica com o efeito de `data`, acima)
  useEffect(() => {
    const m = mapRef.current
    if (!m || !readyRef.current) return
    ;(m.getSource(FONTE_TILES.source) as VectorTileSource | undefined)?.setTiles([tilesUrl])
  }, [tilesUrl])

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
    for (const { source } of FONTES) {
      m.setPaintProperty(`${source}-fill`, 'fill-opacity', satellite ? FILL_SAT : FILL_MAP)
      m.setPaintProperty(`${source}-line`, 'line-color', satellite ? '#ffffff' : LINE_COLOR_MAP)
      m.setPaintProperty(`${source}-line`, 'line-width', satellite ? LINE_WIDTH_SAT : LINE_WIDTH_MAP)
    }
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
      <div className="legend" aria-label="Legenda do mapa">
        {legenda.vago && (
          <span>
            <i className="sw" style={{ background: COR_LOTE.vago }} /> Vago
          </span>
        )}
        {legenda.construido && (
          <span>
            <i className="sw" style={{ background: COR_LOTE.construido }} /> Construído
          </span>
        )}
      </div>
    </div>
  )
}

/** Camadas do lote numa fonte: `<source>-fill` e `<source>-line`. */
function addLotLayers(m: MLMap, f: FonteLote) {
  const base = { source: f.source, ...(f.sourceLayer ? { 'source-layer': f.sourceLayer } : {}), ...f.zoom }
  m.addLayer({
    id: `${f.source}-fill`,
    type: 'fill',
    ...base,
    paint: {
      'fill-color': FILL_COLOR,
      'fill-opacity': FILL_MAP,
    },
  })
  m.addLayer({
    id: `${f.source}-line`,
    type: 'line',
    ...base,
    paint: {
      'line-color': LINE_COLOR_MAP,
      'line-width': LINE_WIDTH_MAP,
    },
  })
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
