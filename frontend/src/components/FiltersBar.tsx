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
    <div className="filters">
      <label className="field">
        <span>Bairro</span>
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

      <label className="field">
        <span>Área m²</span>
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
        <span className="dash">–</span>
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
      </label>

      <label className="field">
        <span>Ordenar por</span>
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
          {value.aVenda && (
            <optgroup label="Preço pedido">
              <option value="preco_asc">menor → maior</option>
              <option value="preco_desc">maior → menor</option>
              <option value="preco_m2_asc">R$/m² do terreno: menor → maior</option>
              <option value="preco_m2_desc">R$/m² do terreno: maior → menor</option>
            </optgroup>
          )}
        </select>
      </label>

      <label className="check">
        <input
          type="checkbox"
          checked={value.onlyVacant}
          onChange={(e) => set({ onlyVacant: e.target.checked })}
        />
        Só vagos
      </label>

      <label className="check" title="Lotes com anúncio ativo (terreno ou casa) coletado nos portais">
        <input
          type="checkbox"
          checked={value.aVenda}
          onChange={(e) => {
            const aVenda = e.target.checked
            // ordenação por preço só existe com anúncio: desligou → volta pra padrão
            const sort = !aVenda && value.sort.startsWith('preco') ? 'none' : value.sort
            set({ aVenda, sort })
          }}
        />
        À venda
      </label>
    </div>
  )
}
