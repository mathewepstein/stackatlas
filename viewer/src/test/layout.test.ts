import ELK from 'elkjs/lib/elk.bundled.js'
import { layout, NODE_HEIGHT, NODE_WIDTH } from '../layout'
import { DEFAULT_FILTERS, column, visible } from '../model'
import { acme } from './fixtures'

describe('layout', () => {
  it('places every visible node in left-to-right column order', async () => {
    const { nodes, edges } = visible(acme(), { ...DEFAULT_FILTERS, hiddenKinds: [] })
    const positions = await layout(nodes, edges, new ELK())
    expect(positions.size).toBe(nodes.length)
    const byColumn = new Map<number, number[]>()
    for (const node of nodes) {
      const xs = byColumn.get(column(node)) ?? []
      xs.push(positions.get(node.id)!.x)
      byColumn.set(column(node), xs)
    }
    const columns = [...byColumn.keys()].sort((a, b) => a - b)
    for (let i = 1; i < columns.length; i++) {
      const left = Math.max(...byColumn.get(columns[i - 1])!)
      const right = Math.min(...byColumn.get(columns[i])!)
      expect(right).toBeGreaterThanOrEqual(left + NODE_WIDTH)
    }
  })

  it('does not overlap nodes', async () => {
    const { nodes, edges } = visible(acme(), DEFAULT_FILTERS)
    const positions = [...(await layout(nodes, edges, new ELK())).values()]
    for (let i = 0; i < positions.length; i++) {
      for (let j = i + 1; j < positions.length; j++) {
        const a = positions[i]
        const b = positions[j]
        const apart =
          Math.abs(a.x - b.x) >= NODE_WIDTH || Math.abs(a.y - b.y) >= NODE_HEIGHT
        expect(apart).toBe(true)
      }
    }
  })
})
