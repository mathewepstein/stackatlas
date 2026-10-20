import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  applyNodeChanges,
  useReactFlow,
  type Edge as FlowEdge,
  type Node as FlowNode,
  type NodeChange,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useEffect, useMemo, useState } from 'react'
import type { Edge, Kind, Node } from '../graph-types'
import { layout } from '../layout'
import { displayName, edgeId, highlight, observedState, type Selection } from '../model'

type AtlasData = { label: string; kind: Kind; dim: boolean; focus: boolean }
type AtlasNode = FlowNode<AtlasData, 'atlas'>

function AtlasNodeView({ data }: NodeProps<AtlasNode>) {
  const classes = ['atlas-node', `kind-${data.kind}`, data.dim && 'dim', data.focus && 'focus']
  return (
    <div className={classes.filter(Boolean).join(' ')} title={data.label}>
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <span className="label">{data.label}</span>
      <span className="kind">{data.kind}</span>
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  )
}

const nodeTypes = { atlas: AtlasNodeView }

interface Props {
  nodes: Node[]
  edges: Edge[]
  selection: Selection
  hops: number
  onSelect: (selection: Selection) => void
  onLayout: (ms: number) => void
}

export function GraphCanvas({ nodes, edges, selection, hops, onSelect, onLayout }: Props) {
  const { fitView } = useReactFlow()
  const [positions, setPositions] = useState<Map<string, { x: number; y: number }> | null>(null)
  const [flowNodes, setFlowNodes] = useState<AtlasNode[]>([])
  const shape = useMemo(
    () => nodes.map((n) => n.id).join('\n') + '\n\n' + edges.map(edgeId).join('\n'),
    [nodes, edges],
  )

  useEffect(() => {
    let live = true
    const start = performance.now()
    layout(nodes, edges).then((result) => {
      if (!live) return
      setPositions(result)
      onLayout(performance.now() - start)
      requestAnimationFrame(() => fitView({ padding: 0.1 }))
    })
    return () => {
      live = false
    }
  }, [shape])

  const lit = useMemo(() => highlight(edges, selection, hops), [edges, selection, hops])
  const focus = selection && 'node' in selection ? selection.node : null

  useEffect(() => {
    if (!positions) return
    setFlowNodes(
      nodes.map((n) => ({
        id: n.id,
        type: 'atlas',
        position: positions.get(n.id) ?? { x: 0, y: 0 },
        data: {
          label: displayName(n),
          kind: n.kind,
          dim: lit !== null && !lit.nodes.has(n.id),
          focus: focus === n.id,
        },
      })),
    )
  }, [positions, lit, focus])

  const flowEdges: FlowEdge[] = useMemo(
    () =>
      edges
        .filter((e) => e.source !== e.target)
        .map((e) => {
          const id = edgeId(e)
          const dim = lit !== null && !lit.edges.has(id)
          return {
            id,
            source: e.source,
            target: e.target,
            className: [
              'atlas-edge',
              `conf-${e.confidence}`,
              `obs-${observedState(e)}`,
              `type-${e.type}`,
              dim ? 'dim' : lit ? 'lit' : '',
            ].join(' '),
            markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
            zIndex: lit && !dim ? 1 : 0,
          }
        }),
    [edges, lit],
  )

  return (
    <ReactFlow
      nodes={flowNodes}
      edges={flowEdges}
      nodeTypes={nodeTypes}
      onNodesChange={(changes: NodeChange<AtlasNode>[]) =>
        setFlowNodes((current) => applyNodeChanges(changes, current))
      }
      onNodeClick={(_, node) => onSelect({ node: node.id })}
      onEdgeClick={(_, edge) => onSelect({ edge: edge.id })}
      onPaneClick={() => onSelect(null)}
      nodesConnectable={false}
      minZoom={0.05}
      colorMode="system"
    >
      <Background />
      <Controls showInteractive={false} />
      <MiniMap pannable zoomable />
    </ReactFlow>
  )
}
