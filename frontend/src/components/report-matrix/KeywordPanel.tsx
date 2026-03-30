import type { KeywordSummary } from '../../types/matrix-report'

interface KeywordPanelProps {
  keywords: KeywordSummary
}

function KwList({ items, polarity }: { items: KeywordSummary['strengths']; polarity: 'strength' | 'weakness' }) {
  const isStrength = polarity === 'strength'
  return (
    <div>
      <h4 className={`mb-2 text-xs font-bold ${isStrength ? 'text-fin-success' : 'text-fin-danger'}`}>
        {isStrength ? '強み' : '懸念'}
      </h4>
      <ul className="space-y-1.5">
        {items.map((kw) => (
          <li key={kw.text} className="flex items-center justify-between gap-2">
            <span className="text-sm text-fin-ink">{kw.text}</span>
            <span className={`min-w-[1.5rem] rounded-full px-1.5 py-0.5 text-center text-[10px] font-bold tabular-nums ${
              isStrength ? 'bg-fin-success/10 text-fin-success' : 'bg-fin-danger/10 text-fin-danger'
            }`}>
              {kw.count}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function KeywordPanel({ keywords }: KeywordPanelProps) {
  return (
    <div className="grid grid-cols-2 gap-4 rounded-[1.5rem] border border-fin-border bg-fin-surface p-5">
      <KwList items={keywords.strengths} polarity="strength" />
      <KwList items={keywords.weaknesses} polarity="weakness" />
    </div>
  )
}
