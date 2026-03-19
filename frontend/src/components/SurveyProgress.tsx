interface Props {
  completed: number
  total: number
  failed: number
  averageScore?: number
}

export default function SurveyProgress({ completed, total, failed, averageScore }: Props) {
  const pct = total > 0 ? Math.round(completed / total * 100) : 0
  const remaining = total - completed - failed

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-fin-panel">
          <div
            className="h-full bg-fin-accent transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="w-12 text-right text-sm font-bold tabular-nums text-fin-ink">{pct}%</span>
      </div>

      <div className="flex gap-4 text-xs text-fin-muted">
        <span>完了: <span className="font-bold text-fin-success">{completed}</span></span>
        <span>待機中: <span className="font-bold text-fin-ink">{remaining}</span></span>
        {failed > 0 && <span>失敗: <span className="font-bold text-fin-danger">{failed}</span></span>}
        {averageScore !== undefined && (
          <span className="ml-auto">
            平均スコア: <span className="font-bold text-fin-accent">{averageScore.toFixed(1)}</span>
          </span>
        )}
      </div>
    </div>
  )
}
