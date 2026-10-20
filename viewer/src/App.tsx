import { useEffect, useMemo, useState } from 'react'
import { FiltersBar } from './components/FiltersBar'
import { GraphCanvas } from './components/GraphCanvas'
import { SidePanel } from './components/SidePanel'
import { UnresolvedTab } from './components/UnresolvedTab'
import type { Graph, Unresolved } from './graph-types'
import { visible, type Filters, type Selection } from './model'
import { decodeHash, encodeHash, type Tab } from './url'

interface Data {
  graph: Graph
  unresolved: Unresolved[]
}

async function fetchData(): Promise<Data> {
  const response = await fetch('graph.json')
  if (!response.ok) throw new Error(`graph.json: HTTP ${response.status}`)
  const graph = (await response.json()) as Graph
  const extra = await fetch('unresolved.json').catch(() => null)
  const unresolved = extra?.ok ? ((await extra.json()) as Unresolved[]) : []
  return { graph, unresolved }
}

async function readFiles(files: FileList): Promise<Data> {
  const byName = new Map([...files].map((f) => [f.name, f]))
  const graphFile = byName.get('graph.json') ?? files[0]
  const graph = JSON.parse(await graphFile.text()) as Graph
  const extra = byName.get('unresolved.json')
  const unresolved = extra ? (JSON.parse(await extra.text()) as Unresolved[]) : []
  return { graph, unresolved }
}

export function App() {
  const initial = useMemo(() => decodeHash(window.location.hash), [])
  const [data, setData] = useState<Data | null>(null)
  const [error, setError] = useState('')
  const [filters, setFilters] = useState<Filters>(initial.filters)
  const [selection, setSelection] = useState<Selection>(initial.selection)
  const [tab, setTab] = useState<Tab>(initial.tab)
  const [layoutMs, setLayoutMs] = useState<number | null>(null)

  useEffect(() => {
    fetchData().then(setData, (e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    const hash = encodeHash(filters, selection, tab)
    if (hash !== window.location.hash) {
      history.replaceState(null, '', hash || window.location.pathname + window.location.search)
    }
  }, [filters, selection, tab])

  useEffect(() => {
    const onHash = () => {
      const state = decodeHash(window.location.hash)
      setFilters(state.filters)
      setSelection(state.selection)
      setTab(state.tab)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const shown = useMemo(() => (data ? visible(data.graph, filters) : null), [data, filters])

  if (!data || !shown) {
    return (
      <main className="loader">
        <h1>stackatlas</h1>
        {error ? (
          <>
            <p>Could not load {error}. Run `stackatlas serve ./out`, or open the files here:</p>
            <input
              type="file"
              accept=".json,application/json"
              multiple
              aria-label="graph.json and unresolved.json"
              onChange={(e) =>
                e.target.files?.length &&
                readFiles(e.target.files).then(setData, (err: Error) => setError(err.message))
              }
            />
          </>
        ) : (
          <p>Loading graph…</p>
        )}
      </main>
    )
  }

  const { graph, unresolved } = data
  return (
    <div className="app">
      <header>
        <h1>stackatlas</h1>
        <span className="org">{graph.org}</span>
        <span className="small">{graph.generatedAt.slice(0, 16).replace('T', ' ')}</span>
        <nav role="tablist">
          <button role="tab" aria-selected={tab === 'graph'} onClick={() => setTab('graph')}>
            Graph
          </button>
          <button
            role="tab"
            aria-selected={tab === 'unresolved'}
            onClick={() => setTab('unresolved')}
          >
            Unresolved ({unresolved.length})
          </button>
        </nav>
        <span className="status small">
          {shown.nodes.length}/{graph.nodes.length} nodes · {shown.edges.length}/
          {graph.edges.length} edges
          {layoutMs !== null && <> · layout {Math.round(layoutMs)} ms</>}
        </span>
      </header>
      {tab === 'graph' ? (
        <div className="workspace">
          <FiltersBar graph={graph} filters={filters} onChange={setFilters} />
          <section className="canvas" aria-label="Graph">
            <GraphCanvas
              nodes={shown.nodes}
              edges={shown.edges}
              selection={selection}
              hops={filters.hops}
              onSelect={setSelection}
              onLayout={setLayoutMs}
            />
          </section>
          <SidePanel graph={graph} selection={selection} onSelect={setSelection} />
        </div>
      ) : (
        <UnresolvedTab items={unresolved} />
      )}
    </div>
  )
}
