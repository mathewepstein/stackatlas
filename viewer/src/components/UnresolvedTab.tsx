import type { Unresolved } from '../graph-types'

export function UnresolvedTab({ items }: { items: Unresolved[] }) {
  if (items.length === 0) return <p className="unresolved empty">Everything resolved.</p>
  return (
    <div className="unresolved">
      <p className="small">
        References that matched no repo. Add them under <code>aliases:</code> in stackatlas.yml.
      </p>
      <table>
        <thead>
          <tr>
            <th>Ref</th>
            <th>Kind</th>
            <th>Count</th>
            <th>Repos</th>
            <th>First evidence</th>
          </tr>
        </thead>
        <tbody>
          {items.map((u) => {
            const first = u.evidence[0]
            const label = first ? `${first.path}:${first.line}` : ''
            return (
              <tr key={`${u.kind}:${u.ref}`}>
                <td className="mono">{u.ref}</td>
                <td>{u.kind}</td>
                <td className="num">{u.count}</td>
                <td>{u.repos.join(', ')}</td>
                <td className="mono small">
                  {first?.url ? (
                    <a href={first.url} target="_blank" rel="noreferrer">
                      {label}
                    </a>
                  ) : (
                    label
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
