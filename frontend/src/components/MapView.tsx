import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import type { FeatureCollection, Geometry } from 'geojson'
import type { GeoJSONSource, Map as MLMap, StyleSpecification } from 'maplibre-gl'

// Basemap claro sem chave (CARTO Positron) — combina com "software técnico claro".
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
  },
  layers: [{ id: 'carto', type: 'raster', source: 'carto' }],
}

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
          'fill-color': ['case', ['get', 'a_venda'], '#0f766e', '#7c878d'],
          'fill-opacity': [
            'case',
            ['boolean', ['feature-state', 'selected'], false],
            0.6,
            ['case', ['get', 'a_venda'], 0.45, 0.22],
          ],
        },
      })
      m.addLayer({
        id: 'lots-line',
        type: 'line',
        source: 'lots',
        paint: {
          'line-color': [
            'case',
            ['boolean', ['feature-state', 'selected'], false],
            '#0b3d39',
            '#516068',
          ],
          'line-width': [
            'case',
            ['boolean', ['feature-state', 'selected'], false],
            2.5,
            0.5,
          ],
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

  return (
    <div className="map-wrap">
      <div ref={containerRef} className="map" />
      <div className="legend">
        <span>
          <i className="sw vago" /> Vago
        </span>
        <span>
          <i className="sw venda" /> À venda
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
