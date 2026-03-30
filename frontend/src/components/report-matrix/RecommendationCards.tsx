import type { Recommendation } from '../../types/matrix-report'

interface RecommendationCardsProps {
  recommendations: Recommendation[]
}

export default function RecommendationCards({ recommendations }: RecommendationCardsProps) {
  if (recommendations.length === 0) {
    return (
      <div className="rounded-[1.5rem] border border-fin-border bg-fin-surface p-5 text-center text-sm text-fin-muted">
        提案を生成中...
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {recommendations.map((rec, i) => (
        <div
          key={rec.highlight_tag + rec.title}
          className="rounded-[1.5rem] border border-fin-border bg-fin-surface p-5"
        >
          <div className="mb-1.5 flex items-center gap-2">
            <span className="rounded-full bg-fin-accent/10 px-2.5 py-0.5 text-xs font-bold text-fin-accent">
              {rec.highlight_tag}
            </span>
            <h4 className="text-sm font-bold text-fin-ink">{rec.title}</h4>
          </div>
          <p className="text-sm text-fin-muted">{rec.body}</p>
        </div>
      ))}
    </div>
  )
}
