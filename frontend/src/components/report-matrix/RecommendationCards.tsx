import type { Recommendation } from '../../types/matrix-report'

interface RecommendationCardsProps {
  recommendations: Recommendation[]
}

const NUMBERED_PREFIXES = ['①', '②', '③', '④', '⑤']

export default function RecommendationCards({ recommendations }: RecommendationCardsProps) {
  if (recommendations.length === 0) {
    return (
      <div className="rounded-[1.5rem] border border-fin-border bg-fin-surface p-5 text-center text-sm text-fin-muted">
        提案を生成中...
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      {recommendations.map((rec, index) => (
        <div
          key={rec.highlight_tag + rec.title}
          className="rounded-2xl border border-fin-border bg-fin-surface p-4"
        >
          <p className="text-sm font-bold text-fin-ink">
            {NUMBERED_PREFIXES[index] ?? ''}{rec.title}
          </p>
          <span className="mt-2 inline-block rounded-full bg-fin-accent/10 px-2.5 py-0.5 text-xs font-bold text-fin-accent">
            {rec.highlight_tag}
          </span>
          <p className="mt-2 text-xs text-fin-muted">{rec.body}</p>
        </div>
      ))}
    </div>
  )
}
