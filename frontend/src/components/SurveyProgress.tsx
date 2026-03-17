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
      {/* Progress bar */}
      <div className="flex items-center gap-3">
        <div className="flex-1 bg-[#141420] rounded-full h-2 overflow-hidden">
          <div
            className="h-full bg-[#76B900] transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="text-sm font-bold text-white w-12 text-right">{pct}%</span>
      </div>

      {/* Stats */}
      <div className="flex gap-4 text-xs text-gray-500">
        <span>完了: <span className="text-green-400 font-bold">{completed}</span></span>
        <span>待機中: <span className="text-gray-400 font-bold">{remaining}</span></span>
        {failed > 0 && <span>失敗: <span className="text-red-400 font-bold">{failed}</span></span>}
        {averageScore !== undefined && (
          <span className="ml-auto">
            平均スコア: <span className="text-[#76B900] font-bold">{averageScore.toFixed(1)}</span>
          </span>
        )}
      </div>
    </div>
  )
}
