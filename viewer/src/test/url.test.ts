import { DEFAULT_FILTERS } from '../model'
import { decodeHash, encodeHash } from '../url'

describe('url state', () => {
  it('defaults encode to an empty hash', () => {
    expect(encodeHash(DEFAULT_FILTERS, null, 'graph')).toBe('')
    expect(decodeHash('')).toEqual({ filters: DEFAULT_FILTERS, selection: null, tab: 'graph' })
  })

  it('round-trips filters, selection and tab', () => {
    const filters = {
      ...DEFAULT_FILTERS,
      hiddenKinds: [],
      layers: ['service', 'orchestration'],
      edgeTypes: ['http' as const],
      confidence: ['exact' as const, 'observed' as const],
      observed: ['not-seen' as const],
      env: 'prod',
      search: 'orders svc',
      hops: 3,
    }
    const selection = { node: 'repo:platform-mono/web/portal-ui' }
    const hash = encodeHash(filters, selection, 'unresolved')
    expect(decodeHash(hash)).toEqual({ filters, selection, tab: 'unresolved' })
  })

  it('round-trips an edge selection', () => {
    const selection = { edge: 'repo:a|repo:b|http' }
    expect(decodeHash(encodeHash(DEFAULT_FILTERS, selection, 'graph')).selection).toEqual(selection)
  })

  it('ignores junk', () => {
    const state = decodeHash('#hops=99&tab=nope&kind=bogus,repo&sel=x')
    expect(state.filters.hops).toBe(3)
    expect(state.tab).toBe('graph')
    expect(state.selection).toBeNull()
  })
})
