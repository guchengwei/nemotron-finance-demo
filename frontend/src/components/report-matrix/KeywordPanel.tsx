import type { KeywordSummary } from '../../types/matrix-report'

interface KeywordPanelProps {
  keywords: KeywordSummary
}

function KwList({ items, polarity }: { items: KeywordSummary['strengths']; polarity: 'strength' | 'weakness' }) {
  const isStrength = polarity === 'strength'
  return (
    <div className="shadow-card rounded-2xl border border-fin-border bg-fin-surface p-4">
      <h4 className={`mb-3 text-sm font-bold ${isStrength ? 'text-fin-success' : 'text-fin-danger'}`}>
        {isStrength ? '強み' : '懸念'}
      </h4>
      <div className="space-y-3">
        {items.map((kw) => (
          <div key={kw.text}>
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-fin-ink">{kw.text}</span>
              <span className={`text-fin-accent font-bold tabular-nums`}>
                ×{kw.count}
              </span>
            </div>
            {kw.elaboration && (
              <p className="mt-1 text-xs text-fin-muted">{kw.elaboration}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function KeywordPanel({ keywords }: KeywordPanelProps) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <KwList items={keywords.strengths} polarity="strength" />
      <KwList items={keywords.weaknesses} polarity="weakness" />
    </div>
  )
}
