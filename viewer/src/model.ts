import type { Edge, Graph, Kind, Node } from './graph-types'

export type ObservedState = 'seen' | 'not-seen' | 'uncovered'
export type Selection = { node: string } | { edge: string } | null

export interface Filters {
  hiddenKinds: Kind[]
  layers: string[]
  edgeTypes: Edge['type'][]
  confidence: Edge['confidence'][]
  observed: ObservedState[]
  env: string
  search: string
  hops: number
}

export const DEFAULT_HIDDEN: Kind[] = ['external', 'function', 'queue', 'topic', 'bucket']

export const DEFAULT_FILTERS: Filters = {
  hiddenKinds: DEFAULT_HIDDEN,
  layers: [],
  edgeTypes: [],
  confidence: [],
  observed: [],
  env: '',
  search: '',
  hops: 1,
}

const COLUMN: Record<Kind, number> = {
  frontend: 0,
  gateway: 1,
  service: 3,
  group: 3,
  library: 3,
  unknown: 3,
  infra: 3,
  function: 4,
  workload: 4,
  datastore: 5,
  queue: 5,
  topic: 5,
  bucket: 5,
  external: 6,
}

export function column(node: Node): number {
  return node.layer === 'orchestration' ? 2 : COLUMN[node.kind]
}

export function edgeId(edge: Edge): string {
  return `${edge.source}|${edge.target}|${edge.type}`
}

export function observedState(edge: Edge): ObservedState {
  if (edge.observed === true) return 'seen'
  if (edge.observed === false) return 'not-seen'
  return 'uncovered'
}

function allows<T>(list: T[], value: T): boolean {
  return list.length === 0 || list.includes(value)
}

export function visible(graph: Graph, filters: Filters): { nodes: Node[]; edges: Edge[] } {
  let nodes = graph.nodes.filter(
    (n) => !filters.hiddenKinds.includes(n.kind) && allows(filters.layers, n.layer),
  )
  const ids = new Set(nodes.map((n) => n.id))
  let edges = graph.edges.filter(
    (e) =>
      ids.has(e.source) &&
      ids.has(e.target) &&
      allows(filters.edgeTypes, e.type) &&
      allows(filters.confidence, e.confidence) &&
      allows(filters.observed, observedState(e)) &&
      (!filters.env || e.envs.length === 0 || e.envs.includes(filters.env)),
  )
  const query = filters.search.trim().toLowerCase()
  const hits = query
    ? new Set(nodes.filter((n) => matches(n, query)).map((n) => n.id))
    : null
  if (hits) edges = edges.filter((e) => hits.has(e.source) || hits.has(e.target))
  const edgeFiltered =
    filters.edgeTypes.length + filters.confidence.length + filters.observed.length > 0 ||
    filters.env !== ''
  if (hits || edgeFiltered) {
    const keep = new Set(edges.flatMap((e) => [e.source, e.target]))
    hits?.forEach((id) => keep.add(id))
    nodes = nodes.filter((n) => keep.has(n.id))
  }
  return { nodes, edges }
}

function matches(node: Node, query: string): boolean {
  return node.id.toLowerCase().includes(query) || node.name.toLowerCase().includes(query)
}

export function highlight(
  edges: Edge[],
  selection: Selection,
  hops: number,
): { nodes: Set<string>; edges: Set<string> } | null {
  if (!selection) return null
  if ('edge' in selection) {
    const edge = edges.find((e) => edgeId(e) === selection.edge)
    if (!edge) return null
    return { nodes: new Set([edge.source, edge.target]), edges: new Set([selection.edge]) }
  }
  const nodes = new Set([selection.node])
  const lit = new Set<string>()
  for (const [from, to] of [['source', 'target'], ['target', 'source']] as const) {
    let frontier = new Set([selection.node])
    for (let i = 0; i < hops && frontier.size; i++) {
      const next = new Set<string>()
      for (const e of edges) {
        if (frontier.has(e[from]) && !lit.has(edgeId(e))) {
          lit.add(edgeId(e))
          if (!nodes.has(e[to])) next.add(e[to])
          nodes.add(e[to])
        }
      }
      frontier = next
    }
  }
  return { nodes, edges: lit }
}

export function edgeEnvs(graph: Graph): string[] {
  return [...new Set(graph.edges.flatMap((e) => e.envs))].sort()
}

export function displayName(node: Node): string {
  if (!node.parent) return node.name
  return `${node.parent.replace(/^repo:/, '')}/${node.name}`
}
