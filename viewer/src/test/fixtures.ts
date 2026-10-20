import golden from '../../../tests/golden/acme.json'
import type { Edge, Graph } from '../graph-types'

export function acme(): Graph {
  const graph = structuredClone(golden) as unknown as Graph
  graph.generatedAt = '2026-10-20T00:00:00Z'
  return graph
}

export function withRuntime(graph: Graph): Graph {
  const mark = (source: string, target: string, patch: Partial<Edge>) => {
    const edge = graph.edges.find((e) => e.source === source && e.target === target)
    if (!edge) throw new Error(`no edge ${source} -> ${target}`)
    Object.assign(edge, patch)
  }
  const trace = { source: 'datadog', env: 'prod', start: '2026-10-13T00:00:00Z', end: '2026-10-20T00:00:00Z' }
  mark('repo:orders-orchestration', 'repo:orders-service', { observed: true, traces: [trace] })
  mark('repo:billing-api', 'repo:inventory-svc', { observed: false })
  graph.edges.push({
    source: 'repo:orders-orchestration',
    target: 'repo:billing-api',
    type: 'http',
    confidence: 'observed',
    envs: ['prod'],
    evidence: [],
    observed: true,
    traces: [trace],
  })
  return graph
}
