import { useState } from 'react'
import type { ScoreTableRow, AxisConfig } from '../../types/matrix-report'
import { scoreColor } from '../../utils/scoreParser'

const QUADRANT_COLOR: Record<string, string> = {
  '即時採用層': 'bg-fin-accent text-white',
  '潜在採用層': 'bg-fin-success text-white',
  '慎重観察層': 'bg-fin-bronze text-white',
  '様子見層': 'bg-fin-warning text-white',
}

interface ScoreTableProps {
  rows: ScoreTableRow[]
  axes: AxisConfig
  onRowClick?: (row: ScoreTableRow) => void
}

type SortKey = 'name' | 'x_score' | 'y_score' | 'quadrant_label'

function barrierLabel(score: number): string {
  if (score >= 4) return '高'
  if (score >= 2.5) return '中'
  return '低'
}

function barrierColor(label: string): string {
  if (label === '高') return 'text-fin-danger'
  if (label === '中') return 'text-fin-warning'
  return 'text-fin-success'
}

export default function ScoreTable({ rows, axes, onRowClick }: ScoreTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('x_score')
  const [sortDesc, setSortDesc] = useState(true)

  const sorted = [...rows].sort((a, b) => {
    const av = a[sortKey]
    const bv = b[sortKey]
    const cmp = typeof av === 'number' && typeof bv === 'number' ? av - bv : String(av).localeCompare(String(bv))
    return sortDesc ? -cmp : cmp
  })

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDesc(!sortDesc)
    else { setSortKey(key); setSortDesc(true) }
  }

  return (
    <div className="overflow-x-auto rounded-[1.5rem] border border-fin-border bg-fin-surface">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-fin-border bg-fin-canvas">
            <th
              className="cursor-pointer px-4 py-3 text-left text-[10px] font-semibold tracking-[0.12em] uppercase text-fin-muted hover:text-fin-ink select-none"
              onClick={() => handleSort('name')}
            >
              氏名{sortKey === 'name' && <span className="ml-1">{sortDesc ? '↓' : '↑'}</span>}
            </th>
            <th
              className="cursor-pointer px-4 py-3 text-left text-[10px] font-semibold tracking-[0.12em] uppercase text-fin-muted hover:text-fin-ink select-none"
              onClick={() => handleSort('x_score')}
            >
              {axes.x_axis.name}{sortKey === 'x_score' && <span className="ml-1">{sortDesc ? '↓' : '↑'}</span>}
            </th>
            <th
              className="cursor-pointer px-4 py-3 text-left text-[10px] font-semibold tracking-[0.12em] uppercase text-fin-muted hover:text-fin-ink select-none"
              onClick={() => handleSort('y_score')}
            >
              {axes.y_axis.name}{sortKey === 'y_score' && <span className="ml-1">{sortDesc ? '↓' : '↑'}</span>}
            </th>
            <th className="px-4 py-3 text-left text-[10px] font-semibold tracking-[0.12em] uppercase text-fin-muted select-none">
              業種・年齢
            </th>
            <th
              className="cursor-pointer px-4 py-3 text-left text-[10px] font-semibold tracking-[0.12em] uppercase text-fin-muted hover:text-fin-ink select-none"
              onClick={() => handleSort('quadrant_label')}
            >
              分類{sortKey === 'quadrant_label' && <span className="ml-1">{sortDesc ? '↓' : '↑'}</span>}
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => {
            const barrier = barrierLabel(row.y_score)
            const isImmediate = row.quadrant_label === '即時採用層'
            return (
              <tr
                key={row.persona_id}
                className={`border-b border-fin-border/50 last:border-0 ${onRowClick ? 'hover:bg-fin-panel/40 cursor-pointer' : 'hover:bg-fin-canvas/50'}`}
                onClick={() => onRowClick?.(row)}
              >
                <td className="px-4 py-2.5 font-medium text-fin-ink">{row.name}</td>
                <td className="px-4 py-2.5">
                  <span
                    className="inline-flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold text-white"
                    style={{ backgroundColor: scoreColor(row.x_score) }}
                  >
                    {row.x_score}
                  </span>
                </td>
                <td className="px-4 py-2.5">
                  <span className={`text-sm font-semibold ${barrierColor(barrier)}`}>
                    {barrier}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-fin-muted text-xs">
                  {row.industry}・{row.age}歳
                </td>
                <td className="px-4 py-2.5">
                  <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-bold ${QUADRANT_COLOR[row.quadrant_label] || 'bg-fin-border text-fin-ink'}`}>
                    {row.quadrant_label}
                  </span>
                  {isImmediate && <span className="ml-1 text-fin-accent font-bold">★</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
