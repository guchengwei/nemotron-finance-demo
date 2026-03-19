import { useCallback, useEffect, useState } from 'react'
import { useStore } from '../store'
import { api } from '../api'
import DemographicCharts from './DemographicCharts'
import TopPickCard from './TopPickCard'
import { scoreColor } from '../utils/scoreParser'

function ScoreCircle({ score }: { score: number }) {
  const color = scoreColor(Math.round(score))
  return (
    <div
      className="flex h-24 w-24 items-center justify-center rounded-full border-4 bg-fin-surface"
      style={{ borderColor: color }}
    >
      <div className="text-center">
        <div className="text-3xl font-black" style={{ color }}>{score.toFixed(1)}</div>
        <div className="text-[10px] text-fin-muted">/ 5.0</div>
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
  const [error, setError] = useState<string | null>(null)

  const triggerGenerate = useCallback(() => {
    if (!currentRunId) return
    setGenerating(true)
    setError(null)
    api.generateReport(currentRunId)
      .then(setCurrentReport)
      .catch((e: Error) => setError(e.message || 'レポート生成に失敗しました'))
      .finally(() => setGenerating(false))
  }, [currentRunId, setCurrentReport])

  useEffect(() => {
    if (!currentReport && currentRunId) {
      triggerGenerate()
    }
  }, [currentReport, currentRunId, triggerGenerate])

  const report = currentReport

  const handleChatWithPersona = useCallback((uuid: string) => {
    let persona = selectedPersonas.find((p) => p.uuid === uuid) ?? null
    if (!persona && currentHistoryRun) {
      const answer = currentHistoryRun.answers.find((a) => a.persona_uuid === uuid)
      if (answer) {
        try { persona = JSON.parse(answer.persona_full_json) } catch { /* skip */ }
      }
    }
    if (persona) {
      setFollowupPersona(persona)
      setStep(5)
    }
  }, [selectedPersonas, currentHistoryRun, setFollowupPersona, setStep])

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
      <div className="flex flex-col items-center justify-center h-32 gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-fin-accent/20 border-t-fin-accent" />
        <div className="text-sm text-fin-muted">レポートを生成中...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-32 gap-3">
        <div className="text-sm text-fin-danger">{error}</div>
        <button
          onClick={triggerGenerate}
          className="rounded-full border border-fin-accent px-4 py-2 text-xs text-fin-accent hover:bg-fin-accentSoft"
        >
          再試行
        </button>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="flex flex-col items-center justify-center h-32 gap-3">
        <div className="text-sm text-fin-muted">レポートがありません</div>
        {(currentHistoryRun?.status === 'running' || currentHistoryRun?.status === 'failed') && (
          <div className="text-xs text-fin-muted">
            この調査は{currentHistoryRun.status === 'running' ? '実行中に中断' : '失敗'}しました
          </div>
        )}
        <button
          onClick={() => setStep(1)}
          className="text-xs text-fin-accent hover:underline"
        >
          ← 新規調査を開始
        </button>
      </div>
    )
  }

  const theme = surveyTheme || currentHistoryRun?.survey_theme || '—'

  return (
    <div data-testid="report-dashboard-screen" className="space-y-6 max-w-5xl">
      <div className="flex flex-col items-start justify-between gap-4 sm:flex-row">
        <div>
          <h2 className="mb-1 text-xl font-bold tracking-[-0.03em] text-fin-ink">調査レポート</h2>
          <div className="max-w-2xl text-sm text-fin-muted">{theme}</div>
        </div>
        <button
          onClick={handleDownload}
          className="rounded-full border border-fin-border px-3 py-2 text-xs text-fin-muted transition-all duration-200 hover:-translate-y-0.5 hover:border-fin-accent hover:text-fin-accent"
        >
          JSON ダウンロード
        </button>
      </div>

      <div className="rounded-[1.75rem] border border-fin-border bg-fin-surface p-6 shadow-card">
        <div className="flex items-center gap-8">
          {report.overall_score !== undefined && (
            <ScoreCircle score={report.overall_score} />
          )}
          <div className="flex-1">
            {report.group_tendency && (
              <div data-testid="report-group-tendency" className="mb-3">
                <div className="mb-1 text-xs font-semibold tracking-[0.12em] text-fin-accent">グループ傾向</div>
                <div className="text-sm leading-relaxed text-fin-ink">{report.group_tendency}</div>
              </div>
            )}
          </div>
        </div>
      </div>

      {report.conclusion && (
        <div data-testid="report-conclusion" className="rounded-[1.5rem] border border-fin-border bg-fin-panel/70 px-5 py-4">
          <div className="mb-2 text-xs font-semibold tracking-[0.12em] text-fin-accent">総合結論・推奨アクション</div>
          <div className="text-sm leading-relaxed text-fin-ink">{report.conclusion}</div>
        </div>
      )}

      <DemographicCharts report={report} />

      {report.top_picks && report.top_picks.length > 0 ? (
        <div data-testid="report-top-picks">
          <h3 className="mb-3 text-sm font-bold text-fin-ink">注目回答者</h3>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
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
      ) : (
        <div className="rounded-[1.5rem] border border-fin-warning/30 bg-fin-warning/10 px-4 py-3 text-sm text-fin-warning">
          注目回答者を特定できませんでした。回答データが少ない可能性があります。
        </div>
      )}
    </div>
  )
}
