import type { LotFilters, LotSort } from '../api/client'

interface Props {
  bairros: string[]
  value: LotFilters
  onChange: (f: LotFilters) => void
}

export function FiltersBar({ bairros, value, onChange }: Props) {
  const set = (patch: Partial<LotFilters>) => onChange({ ...value, ...patch })
  const hasCustomBairro = value.bairro !== '' && !bairros.includes(value.bairro)

  return (
    <div className="filters" role="group" aria-label="Filtros">
      <label className="field">
        <span className="field-k">Bairro</span>
        <select value={value.bairro} onChange={(e) => set({ bairro: e.target.value })}>
          <option value="">Todos os bairros</option>
          {hasCustomBairro && <option value={value.bairro}>{value.bairro}</option>}
          {bairros.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </label>

      <fieldset className="field">
        <legend className="field-k">Área m²</legend>
        <div className="field-range">
          <input
            className="num"
            type="number"
            inputMode="numeric"
            min={0}
            placeholder="mín"
            aria-label="Área mínima do lote em m²"
            value={value.areaMin}
            onChange={(e) => set({ areaMin: e.target.value })}
          />
          <span className="dash" aria-hidden="true">
            –
          </span>
          <input
            className="num"
            type="number"
            inputMode="numeric"
            min={0}
            placeholder="máx"
            aria-label="Área máxima do lote em m²"
            value={value.areaMax}
            onChange={(e) => set({ areaMax: e.target.value })}
          />
        </div>
      </fieldset>

      <label className="field">
        <span className="field-k">Ordenar por</span>
        <select value={value.sort} onChange={(e) => set({ sort: e.target.value as LotSort })}>
          <option value="none">ordem padrão</option>
          <optgroup label="Área do lote">
            <option value="area_desc">maior → menor</option>
            <option value="area_asc">menor → maior</option>
          </optgroup>
          <optgroup label="Cabe no térreo">
            <option value="proj_desc">maior → menor</option>
            <option value="proj_asc">menor → maior</option>
          </optgroup>
        </select>
      </label>
    </div>
  )
}
