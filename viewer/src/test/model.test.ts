import {
  DEFAULT_FILTERS,
  column,
  displayName,
  edgeEnvs,
  edgeId,
  highlight,
  observedState,
  visible,
} from '../model'
import { acme, withRuntime } from './fixtures'

const ids = (items: { id: string }[]) => items.map((n) => n.id)

describe('visible', () => {
  it('hides external and infra resource kinds by default', () => {
    const { nodes, edges } = visible(acme(), DEFAULT_FILTERS)
    const kinds = new Set(nodes.map((n) => n.kind))
    for (const kind of ['external', 'function', 'bucket'] as const) {
      expect(kinds.has(kind)).toBe(false)
    }
    expect(ids(nodes)).toContain('gateway:edge/public')
    expect(ids(nodes)).toContain('datastore:postgres/orders-db')
    const shown = new Set(ids(nodes))
    expect(edges.every((e) => shown.has(e.source) && shown.has(e.target))).toBe(true)
  })

  it('shows queues and topics that exchange events with a visible node', () => {
    const { nodes, edges } = visible(acme(), DEFAULT_FILTERS)
    expect(ids(nodes)).toContain('queue:orders-events')
    expect(ids(nodes)).toContain('topic:alerts')
    expect(ids(nodes)).toContain('topic:price-changes')
    expect(ids(nodes)).not.toContain('queue:notify-retry')
    expect(edges.map(edgeId)).toContain('topic:alerts|queue:orders-events|event')
    expect(edges.map(edgeId)).toContain('queue:orders-events|repo:orders-orchestration|event')
  })

  it('a queue reached only through a hidden node stays hidden', () => {
    const graph = acme()
    graph.nodes.push({
      id: 'queue:orphan', name: 'orphan', kind: 'queue', layer: 'queue', repo: null, url: null,
      sha: null, parent: null, envs: [], endpoints: [], ci: [],
    })
    graph.edges.push({
      source: 'function:edge/notify', target: 'queue:orphan', type: 'event', confidence: 'exact',
      envs: [], evidence: [], observed: null, traces: [],
    })
    expect(ids(visible(graph, DEFAULT_FILTERS).nodes)).not.toContain('queue:orphan')
    const functions = DEFAULT_FILTERS.hiddenKinds.filter((k) => k !== 'function')
    expect(ids(visible(graph, { ...DEFAULT_FILTERS, hiddenKinds: functions }).nodes)).toContain(
      'queue:orphan',
    )
  })

  it('shows every node when nothing is hidden', () => {
    const graph = acme()
    const { nodes, edges } = visible(graph, { ...DEFAULT_FILTERS, hiddenKinds: [] })
    expect(nodes).toHaveLength(graph.nodes.length)
    expect(edges).toHaveLength(graph.edges.length)
  })

  it('edge filters drop nodes left without edges', () => {
    const graph = withRuntime(acme())
    const { nodes, edges } = visible(graph, { ...DEFAULT_FILTERS, observed: ['not-seen'] })
    expect(edges.map(edgeId)).toEqual(['repo:billing-api|repo:inventory-svc|http'])
    expect(ids(nodes).sort()).toEqual(['repo:billing-api', 'repo:inventory-svc'])
  })

  it('env filter keeps untagged edges', () => {
    const { edges } = visible(acme(), { ...DEFAULT_FILTERS, env: 'dev' })
    expect(edges.every((e) => e.envs.length === 0 || e.envs.includes('dev'))).toBe(true)
    expect(edges.some((e) => e.envs.length === 0)).toBe(true)
    expect(edges.some((e) => e.envs.includes('prod') && !e.envs.includes('dev'))).toBe(false)
  })

  it('confidence and type filters', () => {
    const graph = withRuntime(acme())
    const only = visible(graph, { ...DEFAULT_FILTERS, confidence: ['observed'] })
    expect(only.edges.map(edgeId)).toEqual(['repo:orders-orchestration|repo:billing-api|http'])
    const deploys = visible(graph, { ...DEFAULT_FILTERS, edgeTypes: ['deploy'] })
    expect(deploys.edges.every((e) => e.type === 'deploy')).toBe(true)
  })

  it('search keeps matches and their direct neighbours', () => {
    const { nodes } = visible(acme(), { ...DEFAULT_FILTERS, search: 'Inventory' })
    expect(ids(nodes).sort()).toEqual([
      'repo:billing-api',
      'repo:inventory-svc',
      'repo:orders-orchestration',
      'repo:orders-service',
      'repo:platform-mono/admin-api',
      'repo:pricing-svc',
      'topic:inventory-updates',
    ])
  })

  it('layer filter', () => {
    const { nodes } = visible(acme(), { ...DEFAULT_FILTERS, layers: ['orchestration'] })
    expect(ids(nodes)).toEqual(['repo:orders-orchestration'])
  })
})

describe('highlight', () => {
  const { edges } = visible(acme(), { ...DEFAULT_FILTERS, hiddenKinds: [] })

  it('walks up and downstream by hops', () => {
    const one = highlight(edges, { node: 'repo:orders-service' }, 1)!
    expect([...one.nodes].sort()).toEqual([
      'datastore:postgres/orders-db',
      'queue:orders-events',
      'repo:inventory-svc',
      'repo:orders-orchestration',
      'repo:orders-service',
      'repo:platform-mono/portal-api',
      'repo:pricing-svc',
    ])
    const two = highlight(edges, { node: 'repo:orders-service' }, 2)!
    expect(two.nodes.has('repo:gateway-node')).toBe(true)
    expect(two.nodes.has('repo:platform-mono/web/portal-ui')).toBe(true)
    expect(one.nodes.has('repo:gateway-node')).toBe(false)
  })

  it('downstream walk does not climb back up', () => {
    const lit = highlight(edges, { node: 'repo:inventory-svc' }, 3)!
    expect(lit.nodes.has('repo:pricing-svc')).toBe(true)
    expect(lit.nodes.has('external:api.exchangerate.host')).toBe(true)
    expect(lit.edges.has('repo:billing-api|repo:pricing-svc|http')).toBe(false)
  })

  it('edge selection lights only that edge', () => {
    const id = 'repo:orders-orchestration|repo:orders-service|http'
    const lit = highlight(edges, { edge: id }, 3)!
    expect([...lit.edges]).toEqual([id])
    expect([...lit.nodes].sort()).toEqual(['repo:orders-orchestration', 'repo:orders-service'])
  })

  it('nothing selected', () => {
    expect(highlight(edges, null, 1)).toBeNull()
  })
})

describe('helpers', () => {
  it('columns follow the layer order', () => {
    const byId = Object.fromEntries(acme().nodes.map((n) => [n.id, n]))
    expect(column(byId['repo:web-portal'])).toBe(0)
    expect(column(byId['gateway:edge/public'])).toBe(1)
    expect(column(byId['repo:orders-orchestration'])).toBe(2)
    expect(column(byId['repo:orders-service'])).toBe(3)
    expect(column(byId['function:edge/notify'])).toBe(4)
    expect(column(byId['datastore:postgres/orders-db'])).toBe(5)
    expect(column(byId['external:hooks.slack.com'])).toBe(6)
  })

  it('observed state', () => {
    const graph = withRuntime(acme())
    const states = graph.edges.map(observedState)
    expect(states.filter((s) => s === 'seen')).toHaveLength(2)
    expect(states.filter((s) => s === 'not-seen')).toHaveLength(1)
  })

  it('envs and names', () => {
    const graph = acme()
    expect(edgeEnvs(graph)).toEqual(['dev', 'prod'])
    const sub = graph.nodes.find((n) => n.id === 'repo:platform-mono/web/portal-ui')!
    expect(displayName(sub)).toBe('platform-mono/portal-ui')
  })
})
