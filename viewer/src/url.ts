import type { Edge, Kind } from './graph-types'
import { DEFAULT_FILTERS, DEFAULT_HIDDEN, type Filters, type ObservedState, type Selection } from './model'

export type Tab = 'graph' | 'unresolved'

const KINDS: Kind[] = [
  'frontend', 'service', 'infra', 'library', 'group', 'unknown', 'external',
  'gateway', 'function', 'datastore', 'queue', 'topic', 'bucket', 'workload',
]
const TYPES: Edge['type'][] = ['http', 'event', 'deploy', 'datastore', 'depends']
const CONFIDENCE: Edge['confidence'][] = ['exact', 'heuristic', 'observed']
const OBSERVED: ObservedState[] = ['seen', 'not-seen', 'uncovered']

function list(values: string[]): string {
  return values.join(',')
}

function parse<T extends string>(raw: string | null, allowed: readonly T[]): T[] | null {
  if (raw === null) return null
  return raw.split(',').filter((v): v is T => (allowed as readonly string[]).includes(v))
}

function same(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((v) => b.includes(v))
}

export function encodeHash(filters: Filters, selection: Selection, tab: Tab): string {
  const params = new URLSearchParams()
  if (!same(filters.hiddenKinds, DEFAULT_HIDDEN)) params.set('hide', list(filters.hiddenKinds))
  if (filters.layers.length) params.set('layer', list(filters.layers))
  if (filters.edgeTypes.length) params.set('type', list(filters.edgeTypes))
  if (filters.confidence.length) params.set('conf', list(filters.confidence))
  if (filters.observed.length) params.set('obs', list(filters.observed))
  if (filters.env) params.set('env', filters.env)
  if (filters.search) params.set('q', filters.search)
  if (filters.hops !== DEFAULT_FILTERS.hops) params.set('hops', String(filters.hops))
  if (selection && 'node' in selection) params.set('sel', `node:${selection.node}`)
  if (selection && 'edge' in selection) params.set('sel', `edge:${selection.edge}`)
  if (tab !== 'graph') params.set('tab', tab)
  const text = params.toString()
  return text ? `#${text}` : ''
}

export function decodeHash(hash: string): { filters: Filters; selection: Selection; tab: Tab } {
  const params = new URLSearchParams(hash.replace(/^#/, ''))
  const hops = Number(params.get('hops'))
  const filters: Filters = {
    hiddenKinds: parse(params.get('hide'), KINDS) ?? DEFAULT_HIDDEN,
    layers: params.get('layer')?.split(',').filter(Boolean) ?? [],
    edgeTypes: parse(params.get('type'), TYPES) ?? [],
    confidence: parse(params.get('conf'), CONFIDENCE) ?? [],
    observed: parse(params.get('obs'), OBSERVED) ?? [],
    env: params.get('env') ?? '',
    search: params.get('q') ?? '',
    hops: Number.isInteger(hops) && hops >= 1 ? Math.min(hops, 3) : DEFAULT_FILTERS.hops,
  }
  const sel = params.get('sel') ?? ''
  let selection: Selection = null
  if (sel.startsWith('node:')) selection = { node: sel.slice(5) }
  else if (sel.startsWith('edge:')) selection = { edge: sel.slice(5) }
  const tab: Tab = params.get('tab') === 'unresolved' ? 'unresolved' : 'graph'
  return { filters, selection, tab }
}
