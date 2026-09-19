import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import type { FeatureCollection, Geometry } from 'geojson'
import type {
  ExpressionSpecification,
  GeoJSONSource,
  Map as MLMap,
  StyleSpecification,
} from 'maplibre-gl'

// Dois basemaps SEM chave, alternáveis: CARTO Positron (claro, técnico) e Esri World Imagery
// (satélite). O satélite mostra o terreno real visto de cima, com o polígono do lote por cima —
// dá pra ver se está vago, o que há nele e a vizinhança. Esri começa oculto.
const STYLE: StyleSpecification = {
  version: 8,
  sources: {
    carto: {
      type: 'raster',
      tiles: [
        'https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png',
        'https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png',
        'https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png',
      ],
      tileSize: 256,
      attribution: '© OpenStreetMap · © CARTO',
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
    { id: 'carto', type: 'raster', source: 'carto' },
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
  onSelect: (id: number) => void
}

export function MapView({ data, selectedId, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MLMap | null>(null)
  const readyRef = useRef(false)
  const selRef = useRef<number | null>(null)
  const onSelectRef = useRef(onSelect)
  const [satellite, setSatellite] = useState(false)
  useEffect(() => {
    onSelectRef.current = onSelect
  })

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
      if (src && data) {
        src.setData(data)
        fitToData(m, data)
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
    }
  }, [])

  // dados mudaram
  useEffect(() => {
    const m = mapRef.current
    if (!m || !readyRef.current) return
    const src = m.getSource('lots') as GeoJSONSource | undefined
    if (src && data) {
      src.setData(data)
      fitToData(m, data)
    }
  }, [data])

  // seleção mudou
  useEffect(() => {
    const m = mapRef.current
    if (!m || !readyRef.current) return
    if (selRef.current != null) {
      m.removeFeatureState({ source: 'lots', id: selRef.current })
    }
    if (selectedId != null) {
      m.setFeatureState({ source: 'lots', id: selectedId }, { selected: true })
    }
    selRef.current = selectedId
  }, [selectedId])

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
