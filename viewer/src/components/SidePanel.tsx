import type { Edge, Graph, Node } from '../graph-types'
import { displayName, edgeId, observedState, type Selection } from '../model'

const RUNTIME_LABEL = {
  seen: 'Seen in runtime traffic',
  'not-seen': 'Not seen in runtime traffic',
  uncovered: 'No runtime coverage',
}

interface Props {
  graph: Graph
  selection: Selection
  onSelect: (selection: Selection) => void
}

export function SidePanel({ graph, selection, onSelect }: Props) {
  const nodes = new Map(graph.nodes.map((n) => [n.id, n]))
  const name = (id: string) => {
    const node = nodes.get(id)
    return node ? displayName(node) : id
  }
  if (selection && 'node' in selection) {
    const node = nodes.get(selection.node)
    if (node) return <NodePanel graph={graph} node={node} name={name} onSelect={onSelect} />
  }
  if (selection && 'edge' in selection) {
    const edge = graph.edges.find((e) => edgeId(e) === selection.edge)
    if (edge) return <EdgePanel edge={edge} name={name} onSelect={onSelect} />
  }
  return <aside className="panel empty">Select a node or edge to see its evidence.</aside>
}

function NodePanel({
  graph,
  node,
  name,
  onSelect,
}: {
  graph: Graph
  node: Node
  name: (id: string) => string
  onSelect: Props['onSelect']
}) {
  const out = graph.edges.filter((e) => e.source === node.id)
  const into = graph.edges.filter((e) => e.target === node.id)
  const repoLink = node.url ? (node.sha ? `${node.url}/tree/${node.sha}` : node.url) : null
  return (
    <aside className="panel">
      <h2>{displayName(node)}</h2>
      <p className="meta">
        <span className={`badge kind-${node.kind}`}>{node.kind}</span> {node.layer}
        {node.envs.length > 0 && <> · {node.envs.join(', ')}</>}
      </p>
      <p className="mono small">{node.id}</p>
      {repoLink && (
        <p>
          <a href={repoLink} target="_blank" rel="noreferrer">
            {node.url!.replace(/^https:\/\/github\.com\//, '')}
          </a>
          {node.sha && <span className="mono small"> @ {node.sha.slice(0, 7)}</span>}
        </p>
      )}
      {node.endpoints.length > 0 && (
        <section aria-label="Endpoints">
          <h3>Endpoints</h3>
          <ul className="mono small">
            {node.endpoints.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </section>
      )}
      {node.ci.length > 0 && (
        <section aria-label="CI">
          <h3>CI</h3>
          <ul className="small">
            {node.ci.map((c) => (
              <li key={`${c.system}:${c.repo}:${c.path}`}>
                {c.system} <span className="mono">{c.repo ? `${c.repo}/` : ''}{c.path}</span>
                {c.registries.length > 0 && <> → {c.registries.join(', ')}</>}
              </li>
            ))}
          </ul>
        </section>
      )}
      <EdgeList label="Calls" edges={out} other={(e) => e.target} name={name} onSelect={onSelect} />
      <EdgeList label="Called by" edges={into} other={(e) => e.source} name={name} onSelect={onSelect} />
    </aside>
  )
}

function EdgeList({
  label,
  edges,
  other,
  name,
  onSelect,
}: {
  label: string
  edges: Edge[]
  other: (edge: Edge) => string
  name: (id: string) => string
  onSelect: Props['onSelect']
}) {
  if (edges.length === 0) return null
  return (
    <section aria-label={label}>
      <h3>
        {label} ({edges.length})
      </h3>
      <ul className="edge-list">
        {edges.map((e) => (
          <li key={edgeId(e)}>
            <button type="button" onClick={() => onSelect({ edge: edgeId(e) })}>
              {name(other(e))} <span className="small">{e.type} · {e.confidence}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

function EdgePanel({
  edge,
  name,
  onSelect,
}: {
  edge: Edge
  name: (id: string) => string
  onSelect: Props['onSelect']
}) {
  const state = observedState(edge)
  return (
    <aside className="panel">
      <h2 className="edge-title">
        <button type="button" onClick={() => onSelect({ node: edge.source })}>
          {name(edge.source)}
        </button>
        <span aria-hidden="true"> → </span>
        <button type="button" onClick={() => onSelect({ node: edge.target })}>
          {name(edge.target)}
        </button>
      </h2>
      <p className="meta">
        {edge.type} · <span className={`conf-${edge.confidence}`}>{edge.confidence}</span>
        {edge.envs.length > 0 && <> · {edge.envs.join(', ')}</>}
      </p>
      <p className={`runtime runtime-${state}`}>{RUNTIME_LABEL[state]}</p>
      {edge.traces.length > 0 && (
        <ul className="small">
          {edge.traces.map((t) => (
            <li key={`${t.source}:${t.env}`}>
              {t.source} · {t.env} · {t.start.slice(0, 10)} – {t.end.slice(0, 10)}
            </li>
          ))}
        </ul>
      )}
      <section aria-label="Evidence">
        <h3>Evidence ({edge.evidence.length})</h3>
        <ul className="evidence">
          {edge.evidence.map((v) => {
            const label = `${v.path}:${v.line}`
            return (
              <li key={label}>
                {v.url ? (
                  <a href={v.url} target="_blank" rel="noreferrer" className="mono small">
                    {label}
                  </a>
                ) : (
                  <span className="mono small">{label}</span>
                )}
                <code>{v.snippet}</code>
              </li>
            )
          })}
        </ul>
      </section>
    </aside>
  )
}
