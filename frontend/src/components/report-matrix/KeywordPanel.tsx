import type { KeywordSummary } from '../../types/matrix-report'

interface KeywordPanelProps {
  keywords: KeywordSummary
}

const TAG_STYLES = {
  strength: {
    tag: 'rounded-full bg-fin-success/10 px-2.5 py-0.5 text-xs font-medium text-fin-success',
    header: 'text-fin-success',
  },
  weakness: {
    tag: 'rounded-full bg-fin-danger/10 px-2.5 py-0.5 text-xs font-medium text-fin-danger',
    header: 'text-fin-danger',
  },
}

function KwList({ items, polarity }: { items: KeywordSummary['strengths']; polarity: 'strength' | 'weakness' }) {
  const styles = TAG_STYLES[polarity]
  return (
    <div className="shadow-card rounded-2xl border border-fin-border bg-fin-surface p-4">
      <h4 className={`mb-3 text-sm font-bold ${styles.header}`}>
        {polarity === 'strength' ? '強み' : '懸念'}
      </h4>
      <div className="space-y-3">
        {items.map((kw, i) => (
          <div key={kw.text} className={i > 0 ? 'border-t border-fin-border/50 pt-3' : ''}>
            <div className="flex items-center gap-2">
              <span className={styles.tag}>{kw.text}</span>
              <span className="text-[10px] text-fin-muted">×{kw.count}</span>
            </div>
            {kw.elaboration && (
              <p className="mt-1.5 text-xs leading-relaxed text-fin-muted">{kw.elaboration}</p>
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
