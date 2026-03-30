import { useState } from 'react'
import type { ScoreTableRow, AxisConfig } from '../../types/matrix-report'

interface ScoreTableProps {
  rows: ScoreTableRow[]
  axes: AxisConfig
}

type SortKey = 'name' | 'x_score' | 'y_score' | 'quadrant_label'

export default function ScoreTable({ rows, axes }: ScoreTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('x_score')
  const [sortDesc, setSortDesc] = useState(true)

  const sorted = [...rows].sort((a, b) => {
    const av = a[sortKey]
    const bv = b[sortKey]
    const cmp = typeof av === 'number' && typeof bv === 'number' ? av - bv : String(av).localeCompare(String(bv))
    return sortDesc ? -cmp : cmp
  })

  const cols: { key: SortKey; label: string }[] = [
    { key: 'name', label: '名前' },
    { key: 'x_score', label: axes.x_axis.name },
    { key: 'y_score', label: axes.y_axis.name },
    { key: 'quadrant_label', label: '象限' },
  ]

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDesc(!sortDesc)
    else { setSortKey(key); setSortDesc(true) }
  }

  return (
    <div className="overflow-x-auto rounded-[1.5rem] border border-fin-border bg-fin-surface">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-fin-border">
            {cols.map((col) => (
              <th
                key={col.key}
                className="cursor-pointer px-4 py-3 text-left text-xs font-bold text-fin-muted hover:text-fin-ink select-none"
                onClick={() => handleSort(col.key)}
              >
                <span>{col.label}</span>
                {sortKey === col.key && <span className="ml-1">{sortDesc ? '↓' : '↑'}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={row.persona_id} className="border-b border-fin-border/50 last:border-0 hover:bg-fin-canvas/50">
              <td className="px-4 py-2.5 font-medium text-fin-ink">{row.name}</td>
              <td className="px-4 py-2.5 text-fin-ink tabular-nums">{row.x_score}</td>
              <td className="px-4 py-2.5 text-fin-ink tabular-nums">{row.y_score}</td>
              <td className="px-4 py-2.5 text-fin-muted">{row.quadrant_label}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
