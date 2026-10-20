import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { FiltersBar } from '../components/FiltersBar'
import { SidePanel } from '../components/SidePanel'
import { UnresolvedTab } from '../components/UnresolvedTab'
import type { Unresolved } from '../graph-types'
import { DEFAULT_FILTERS } from '../model'
import { acme, withRuntime } from './fixtures'

afterEach(cleanup)

describe('SidePanel', () => {
  it('prompts when nothing is selected', () => {
    render(<SidePanel graph={acme()} selection={null} onSelect={() => {}} />)
    expect(screen.getByText(/select a node or edge/i)).toBeTruthy()
  })

  it('shows a node with its endpoints, ci and edges', () => {
    const onSelect = vi.fn()
    const graph = acme()
    render(<SidePanel graph={graph} selection={{ node: 'gateway:edge/public' }} onSelect={onSelect} />)
    expect(screen.getByRole('heading', { name: 'public-api' })).toBeTruthy()
    expect(screen.getByText('POST /v1/orders/{proxy+}')).toBeTruthy()
    const out = screen.getByRole('region', { name: 'Calls' })
    fireEvent.click(within(out).getByRole('button', { name: /orders-orchestration/ }))
    expect(onSelect).toHaveBeenCalledWith({
      edge: 'gateway:edge/public|repo:orders-orchestration|http',
    })
    const into = screen.getByRole('region', { name: 'Called by' })
    expect(within(into).getByRole('button', { name: /platform-infra/ })).toBeTruthy()
  })

  it('links the repo at its sha', () => {
    const graph = acme()
    const node = graph.nodes.find((n) => n.id === 'repo:orders-service')!
    node.url = 'https://github.com/acme/orders-service'
    node.sha = 'abc123'
    render(<SidePanel graph={graph} selection={{ node: node.id }} onSelect={() => {}} />)
    const link = screen.getByRole('link', { name: /acme\/orders-service/ })
    expect(link.getAttribute('href')).toBe('https://github.com/acme/orders-service/tree/abc123')
  })

  it('shows an edge with evidence, runtime state and traces', () => {
    const graph = withRuntime(acme())
    const edge = graph.edges.find(
      (e) => e.source === 'repo:orders-orchestration' && e.target === 'repo:orders-service',
    )!
    edge.evidence[0].url = 'https://github.com/acme/orders-orchestration/blob/s/x#L5'
    const onSelect = vi.fn()
    render(
      <SidePanel
        graph={graph}
        selection={{ edge: 'repo:orders-orchestration|repo:orders-service|http' }}
        onSelect={onSelect}
      />,
    )
    expect(screen.getByText(/seen in runtime traffic/i)).toBeTruthy()
    expect(screen.getByText(/datadog · prod · 2026-10-13 – 2026-10-20/)).toBeTruthy()
    const link = screen.getByRole('link', { name: 'src/main/java/com/acme/orders/OrdersClient.java:5' })
    expect(link.getAttribute('href')).toBe(edge.evidence[0].url)
    expect(screen.getByText('@FeignClient(name = "orders-service")')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'orders-service' }))
    expect(onSelect).toHaveBeenCalledWith({ node: 'repo:orders-service' })
  })

  it('labels not-seen and uncovered edges', () => {
    const graph = withRuntime(acme())
    const { rerender } = render(
      <SidePanel graph={graph} selection={{ edge: 'repo:billing-api|repo:inventory-svc|http' }} onSelect={() => {}} />,
    )
    expect(screen.getByText(/not seen in runtime traffic/i)).toBeTruthy()
    rerender(
      <SidePanel graph={graph} selection={{ edge: 'repo:billing-api|repo:pricing-svc|http' }} onSelect={() => {}} />,
    )
    expect(screen.getByText(/no runtime coverage/i)).toBeTruthy()
  })
})

describe('UnresolvedTab', () => {
  it('lists refs with counts and first evidence', () => {
    const items: Unresolved[] = [
      { ref: 'sl', kind: 'service', count: 28, repos: [], evidence: [] },
      {
        ref: 'hooks.slack.com',
        kind: 'host',
        count: 1,
        repos: ['notifications-worker'],
        evidence: [{ path: 'worker.py', line: 5, snippet: 'x', url: null }],
      },
    ]
    render(<UnresolvedTab items={items} />)
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows.map((r) => within(r).getAllByRole('cell')[0].textContent)).toEqual(['sl', 'hooks.slack.com'])
    expect(within(rows[1]).getByText('worker.py:5')).toBeTruthy()
    expect(within(rows[1]).getByText('notifications-worker')).toBeTruthy()
  })

  it('says when everything resolved', () => {
    render(<UnresolvedTab items={[]} />)
    expect(screen.getByText(/everything resolved/i)).toBeTruthy()
  })
})

describe('FiltersBar', () => {
  it('toggles kinds', () => {
    const onChange = vi.fn()
    render(<FiltersBar graph={acme()} filters={DEFAULT_FILTERS} onChange={onChange} />)
    const kinds = within(screen.getByRole('group', { name: 'Kinds' }))
    const external = kinds.getByRole('checkbox', { name: 'external' }) as HTMLInputElement
    expect(external.checked).toBe(false)
    fireEvent.click(external)
    expect(onChange.mock.calls[0][0].hiddenKinds).not.toContain('external')
    fireEvent.click(kinds.getByRole('checkbox', { name: 'service' }))
    expect(onChange.mock.calls[1][0].hiddenKinds).toContain('service')
  })

  it('sets search, env, hops and runtime state', () => {
    const onChange = vi.fn()
    render(<FiltersBar graph={acme()} filters={DEFAULT_FILTERS} onChange={onChange} />)
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'orders' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_FILTERS, search: 'orders' })
    fireEvent.change(screen.getByRole('combobox', { name: 'Env' }), { target: { value: 'prod' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_FILTERS, env: 'prod' })
    fireEvent.change(screen.getByRole('combobox', { name: 'Hops' }), { target: { value: '2' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_FILTERS, hops: 2 })
    fireEvent.click(screen.getByRole('checkbox', { name: 'not seen' }))
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_FILTERS, observed: ['not-seen'] })
  })

  it('resets', () => {
    const onChange = vi.fn()
    render(<FiltersBar graph={acme()} filters={{ ...DEFAULT_FILTERS, search: 'x' }} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: 'Reset' }))
    expect(onChange).toHaveBeenLastCalledWith(DEFAULT_FILTERS)
  })
})
