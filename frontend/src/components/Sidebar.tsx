import { useEffect } from 'react'
import { useStore } from '../store'
import { api } from '../api'

function scoreColor(score?: number): string {
  if (!score) return 'bg-gray-700 text-gray-400'
  if (score >= 4.5) return 'bg-[#2563EB] text-black'
  if (score >= 3.5) return 'bg-green-700 text-white'
  if (score >= 2.5) return 'bg-yellow-600 text-white'
  return 'bg-red-700 text-white'
}

export default function Sidebar() {
  const { history, setHistory, setStep, setCurrentReport, setCurrentHistoryRun, resetSurvey } = useStore()
  const dbReady = useStore(s => s.dbReady)

  useEffect(() => {
    api.getHistory().then((r) => setHistory(r.runs)).catch(console.error)
  }, [setHistory])

  const loadRun = async (run_id: string) => {
    try {
      const detail = await api.getHistoryRun(run_id)
      setCurrentHistoryRun(detail)
      if (detail.report) {
        setCurrentReport(detail.report)
      }
      setStep(4)
    } catch (e) {
      console.error('Failed to load run:', e)
    }
  }

  return (
    <aside className="w-56 flex-shrink-0 bg-[#1E293B] border-r border-[rgba(37,99,235,0.1)] flex flex-col h-full">
      <div className="p-4 border-b border-[rgba(37,99,235,0.1)]">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 bg-[#2563EB] rounded flex items-center justify-center">
            <span className="text-black text-xs font-black">N</span>
          </div>
          <div>
            <div className="text-xs font-bold text-[#2563EB]">NEMOTRON</div>
            <div className="text-[10px] text-gray-500">Financial Survey</div>
          </div>
        </div>
      </div>

      <div className="p-3">
        <button
          data-testid="new-survey-button"
          disabled={!dbReady}
          onClick={() => resetSurvey()}
          className={`w-full bg-[#2563EB] hover:bg-[#3B82F6] text-black text-sm font-bold py-2 px-3 rounded transition-colors ${!dbReady ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          ＋ 新規調査
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="px-3 py-1 text-[10px] font-semibold text-gray-600 uppercase tracking-wider">
          調査履歴
        </div>
        {history.length === 0 ? (
          <div className="px-3 py-4 text-xs text-gray-600 text-center">
            履歴はありません
          </div>
        ) : (
          history.map((run) => (
            <button
              key={run.id}
              onClick={() => loadRun(run.id)}
              className="w-full text-left px-3 py-2 hover:bg-[#1E2D40] border-b border-[rgba(255,255,255,0.03)] transition-colors group"
            >
              <div className="flex items-center justify-between mb-1">
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${scoreColor(run.overall_score)}`}>
                  {run.overall_score ? `${run.overall_score}★` : run.status === 'running' ? '実行中' : '—'}
                </span>
                <span className="text-[10px] text-gray-600">
                  {run.persona_count}名
                </span>
              </div>
              <div className="text-xs text-gray-300 line-clamp-2 group-hover:text-white transition-colors">
                {run.label || run.survey_theme}
              </div>
              <div className="text-[10px] text-gray-600 mt-0.5">
                {new Date(run.created_at).toLocaleDateString('ja-JP')}
              </div>
            </button>
          ))
        )}
      </div>
    </aside>
  )
}
