import type { ELK } from 'elkjs/lib/elk-api'
import type { Edge, Node } from './graph-types'
import { column, edgeId } from './model'

export const NODE_WIDTH = 200
export const NODE_HEIGHT = 44

const OPTIONS = {
  'elk.algorithm': 'layered',
  'elk.direction': 'RIGHT',
  'elk.partitioning.activate': 'true',
  'elk.separateConnectedComponents': 'false',
  'elk.layered.spacing.nodeNodeBetweenLayers': '90',
  'elk.spacing.nodeNode': '20',
  'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
}

let shared: ELK | null = null

async function workerElk(): Promise<ELK> {
  if (!shared) {
    const [{ default: Elk }, { default: workerUrl }] = await Promise.all([
      import('elkjs/lib/elk-api'),
      import('elkjs/lib/elk-worker.min.js?url'),
    ])
    shared = new Elk({ workerUrl })
  }
  return shared
}

export async function layout(
  nodes: Node[],
  edges: Edge[],
  elk?: ELK,
): Promise<Map<string, { x: number; y: number }>> {
  const engine = elk ?? (await workerElk())
  const result = await engine.layout({
    id: 'root',
    layoutOptions: OPTIONS,
    children: nodes.map((n) => ({
      id: n.id,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      layoutOptions: { 'elk.partitioning.partition': String(column(n)) },
    })),
    edges: edges
      .filter((e) => e.source !== e.target)
      .map((e) => ({ id: edgeId(e), sources: [e.source], targets: [e.target] })),
  })
  return new Map((result.children ?? []).map((c) => [c.id, { x: c.x ?? 0, y: c.y ?? 0 }]))
}
