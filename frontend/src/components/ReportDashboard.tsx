import { useEffect, useState } from 'react'
import { useStore } from '../store'
import { api } from '../api'
import DemographicCharts from './DemographicCharts'
import TopPickCard from './TopPickCard'
import { scoreColor } from '../utils/scoreParser'

function ScoreCircle({ score }: { score: number }) {
  const color = scoreColor(Math.round(score))
  return (
    <div
      className="w-24 h-24 rounded-full border-4 flex items-center justify-center"
      style={{ borderColor: color }}
    >
      <div className="text-center">
        <div className="text-3xl font-black" style={{ color }}>{score.toFixed(1)}</div>
        <div className="text-[10px] text-gray-500">/ 5.0</div>
      </div>
    </div>
  )
}

export default function ReportDashboard() {
  const {
    currentReport, currentRunId, setCurrentReport, setFollowupPersona,
    setStep, currentHistoryRun, selectedPersonas, surveyTheme
  } = useStore()

  const [generating, setGenerating] = useState(false)

  useEffect(() => {
    if (!currentReport && currentRunId) {
      setGenerating(true)
      api.generateReport(currentRunId)
        .then(setCurrentReport)
        .catch(console.error)
        .finally(() => setGenerating(false))
    }
  }, [currentReport, currentRunId, setCurrentReport])

  const report = currentReport

  const handleChatWithPersona = (uuid: string) => {
    // Find persona from selected or from history
    const persona = selectedPersonas.find((p) => p.uuid === uuid) ||
      currentHistoryRun?.answers.find((a) => a.persona_uuid === uuid)
        ? (() => {
            try {
              return JSON.parse(currentHistoryRun!.answers.find((a) => a.persona_uuid === uuid)!.persona_full_json)
            } catch { return null }
          })()
        : null
    if (persona) setFollowupPersona(persona)
    setStep(5)
  }

  const handleDownload = () => {
    if (!report) return
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `survey-report-${report.run_id?.slice(0, 8) || 'data'}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (generating) {
    return (
      <div className="flex items-center justify-center h-32">
        <div className="text-gray-500 text-sm">レポートを生成中...</div>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="flex items-center justify-center h-32">
        <div className="text-gray-500 text-sm">レポートデータがありません</div>
      </div>
    )
  }

  const theme = surveyTheme || currentHistoryRun?.survey_theme || '—'

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-bold text-white mb-1">調査レポート</h2>
          <div className="text-sm text-gray-400 max-w-2xl">{theme}</div>
        </div>
        <button
          onClick={handleDownload}
          className="text-xs text-gray-500 hover:text-gray-300 border border-[rgba(255,255,255,0.1)] px-3 py-1.5 rounded transition-colors"
        >
          JSON ダウンロード
        </button>
      </div>

      {/* Score overview */}
      <div className="bg-[#1E2D40] border border-[rgba(37,99,235,0.1)] rounded-xl p-6">
        <div className="flex items-center gap-8">
          {report.overall_score !== undefined && (
            <ScoreCircle score={report.overall_score} />
          )}
          <div className="flex-1">
            {report.group_tendency && (
              <div className="mb-3">
                <div className="text-xs font-semibold text-[#2563EB] mb-1">グループ傾向</div>
                <div className="text-sm text-gray-300 leading-relaxed">{report.group_tendency}</div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Conclusion */}
      {report.conclusion && (
        <div className="bg-[#1E293B] border-l-4 border-[#2563EB] rounded-r-lg px-5 py-4">
          <div className="text-xs font-semibold text-[#2563EB] mb-2">総合結論・推奨アクション</div>
          <div className="text-sm text-gray-200 leading-relaxed">{report.conclusion}</div>
        </div>
      )}

      {/* Charts */}
      <DemographicCharts report={report} />

      {/* Top picks */}
      {report.top_picks && report.top_picks.length > 0 && (
        <div>
          <h3 className="text-sm font-bold text-white mb-3">注目回答者</h3>
          <div className="grid grid-cols-3 gap-4">
            {report.top_picks.slice(0, 3).map((pick, i) => {
              const persona = selectedPersonas.find((p) => p.uuid === pick.persona_uuid)
              return (
                <TopPickCard
                  key={i}
                  pick={pick}
                  persona={persona}
                  variant={i === 0 ? 'positive' : i === 1 ? 'negative' : 'unique'}
                  onChat={() => handleChatWithPersona(pick.persona_uuid)}
                />
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
