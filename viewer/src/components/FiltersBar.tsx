import type { Edge, Graph, Kind } from '../graph-types'
import { DEFAULT_FILTERS, column, edgeEnvs, type Filters, type ObservedState } from '../model'

const TYPES: Edge['type'][] = ['http', 'event', 'deploy', 'datastore', 'depends']
const CONFIDENCE: Edge['confidence'][] = ['exact', 'heuristic', 'observed']
const OBSERVED: [ObservedState, string][] = [
  ['seen', 'seen'],
  ['not-seen', 'not seen'],
  ['uncovered', 'no coverage'],
]

interface Props {
  graph: Graph
  filters: Filters
  onChange: (filters: Filters) => void
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value]
}

export function FiltersBar({ graph, filters, onChange }: Props) {
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch })
  const kinds = [...new Map(graph.nodes.map((n) => [n.kind, column(n)])).entries()]
    .sort((a, b) => a[1] - b[1] || a[0].localeCompare(b[0]))
    .map(([kind]) => kind as Kind)
  const layers = [...new Set(graph.nodes.map((n) => n.layer))].sort()
  const types = TYPES.filter((t) => graph.edges.some((e) => e.type === t))
  const envs = edgeEnvs(graph)
  return (
    <div className="filters">
      <input
        type="search"
        placeholder="Search nodes"
        value={filters.search}
        onChange={(e) => set({ search: e.target.value })}
      />
      <fieldset>
        <legend>Kinds</legend>
        {kinds.map((kind) => (
          <label key={kind}>
            <input
              type="checkbox"
              checked={!filters.hiddenKinds.includes(kind)}
              onChange={() => set({ hiddenKinds: toggle(filters.hiddenKinds, kind) })}
            />
            {kind}
          </label>
        ))}
      </fieldset>
      <fieldset>
        <legend>Layers</legend>
        {layers.map((layer) => (
          <label key={layer}>
            <input
              type="checkbox"
              checked={filters.layers.includes(layer)}
              onChange={() => set({ layers: toggle(filters.layers, layer) })}
            />
            {layer}
          </label>
        ))}
      </fieldset>
      <fieldset>
        <legend>Edges</legend>
        {types.map((t) => (
          <label key={t}>
            <input
              type="checkbox"
              checked={filters.edgeTypes.includes(t)}
              onChange={() => set({ edgeTypes: toggle(filters.edgeTypes, t) })}
            />
            {t}
          </label>
        ))}
      </fieldset>
      <fieldset>
        <legend>Confidence</legend>
        {CONFIDENCE.map((c) => (
          <label key={c}>
            <input
              type="checkbox"
              checked={filters.confidence.includes(c)}
              onChange={() => set({ confidence: toggle(filters.confidence, c) })}
            />
            {c}
          </label>
        ))}
      </fieldset>
      <fieldset>
        <legend>Runtime</legend>
        {OBSERVED.map(([state, label]) => (
          <label key={state}>
            <input
              type="checkbox"
              checked={filters.observed.includes(state)}
              onChange={() => set({ observed: toggle(filters.observed, state) })}
            />
            {label}
          </label>
        ))}
      </fieldset>
      <label className="inline">
        Env
        <select aria-label="Env" value={filters.env} onChange={(e) => set({ env: e.target.value })}>
          <option value="">all</option>
          {envs.map((env) => (
            <option key={env} value={env}>
              {env}
            </option>
          ))}
        </select>
      </label>
      <label className="inline">
        Hops
        <select
          aria-label="Hops"
          value={filters.hops}
          onChange={(e) => set({ hops: Number(e.target.value) })}
        >
          {[1, 2, 3].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
      <button type="button" onClick={() => onChange(DEFAULT_FILTERS)}>
        Reset
      </button>
    </div>
  )
}
