import { useEffect, useState } from 'react'
import { useStore } from '../store'
import { api } from '../api'
import type { Persona, PersonaRunState, SurveyRunDetail } from '../types'

function scoreColor(score?: number): string {
  if (!score) return 'bg-gray-700 text-gray-400'
  if (score >= 4.5) return 'bg-[#2563EB] text-black'
  if (score >= 3.5) return 'bg-green-700 text-white'
  if (score >= 2.5) return 'bg-yellow-600 text-white'
  return 'bg-red-700 text-white'
}

function buildPersonaStates(detail: SurveyRunDetail) {
  const personas = new Map<string, Persona>()
  const personaStates: Record<string, PersonaRunState> = {}

  for (const answer of detail.answers) {
    if (!personas.has(answer.persona_uuid)) {
      try {
        personas.set(answer.persona_uuid, JSON.parse(answer.persona_full_json) as Persona)
      } catch {
        continue
      }
    }

    const persona = personas.get(answer.persona_uuid)
    if (!persona) continue

    if (!personaStates[answer.persona_uuid]) {
      personaStates[answer.persona_uuid] = {
        persona,
        status: 'waiting',
        answers: [],
      }
    }

    personaStates[answer.persona_uuid].answers[answer.question_index] = {
      question: answer.question_text,
      answer: answer.answer,
      score: answer.score,
    }
  }

  for (const [, state] of Object.entries(personaStates)) {
    const answeredCount = state.answers.filter(Boolean).length
    if (detail.status === 'completed' && answeredCount === detail.questions.length) {
      state.status = 'complete'
    } else if (answeredCount > 0) {
      state.status = detail.status === 'running' ? 'error' : detail.status === 'failed' ? 'error' : 'complete'
    }
  }

  return {
    personas: Array.from(personas.values()),
    personaStates,
    completed: Object.values(personaStates).filter((state) => state.status === 'complete').length,
    failed: Object.values(personaStates).filter((state) => state.status === 'error').length,
  }
}

export default function Sidebar() {
  const { history, setHistory, setStep, setCurrentReport, setCurrentHistoryRun, resetSurvey, setSelectedPersonas, setQuestions, setSurveyTheme, setSurveyLabel, setCurrentRunId, setPersonaStates, setSurveyComplete, setSurveyCounts } = useStore()
  const dbReady = useStore((s) => s.dbReady)

  useEffect(() => {
    api.getHistory().then((r) => setHistory(r.runs)).catch(console.error)
  }, [setHistory])

  const [deleting, setDeleting] = useState<string | null>(null)

  const deleteRun = async (e: React.MouseEvent, run_id: string) => {
    e.stopPropagation()
    setDeleting(run_id)
    try {
      await api.deleteHistoryRun(run_id)
      setHistory(history.filter((r) => r.id !== run_id))
    } catch (err) {
      console.error('Failed to delete run:', err)
    } finally {
      setDeleting(null)
    }
  }

  const loadRun = async (run_id: string) => {
    try {
      const detail = await api.getHistoryRun(run_id)
      setCurrentHistoryRun(detail)
      setCurrentRunId(detail.id)
      setSurveyTheme(detail.survey_theme)
      setQuestions(detail.questions)
      setSurveyLabel(detail.label || '')

      if (detail.report) {
        setCurrentReport(detail.report)
      } else {
        setCurrentReport(null)
      }

      if (detail.status === 'running' || detail.status === 'failed') {
        const reconstructed = buildPersonaStates(detail)
        setSelectedPersonas(reconstructed.personas)
        setPersonaStates(reconstructed.personaStates)
        setSurveyCounts(reconstructed.completed, reconstructed.failed)
        setSurveyComplete(detail.status !== 'running')
        setStep(3)
        return
      }

      if (detail.report) {
        setStep(4)
        return
      }

      try {
        const report = await api.generateReport(run_id)
        setCurrentReport(report)
      } catch {
        // Leave report empty if generation is impossible.
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
              data-testid={`history-run-${run.id}`}
              onClick={() => loadRun(run.id)}
              className="relative w-full text-left px-3 py-2 hover:bg-[#1E2D40] border-b border-[rgba(255,255,255,0.03)] transition-colors group"
            >
              <div className="flex items-center justify-between mb-1">
                <span
                  data-testid={`history-run-status-${run.id}`}
                  className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${scoreColor(run.overall_score)}`}
                >
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
              <div
                data-testid={`delete-run-${run.id}`}
                role="button"
                onClick={(e) => deleteRun(e, run.id)}
                className="absolute top-1 right-1 w-5 h-5 flex items-center justify-center rounded text-gray-600 hover:text-red-400 hover:bg-red-400/10 opacity-0 group-hover:opacity-100 transition-all text-xs"
                title="削除"
              >
                {deleting === run.id ? '...' : '×'}
              </div>
            </button>
          ))
        )}
      </div>
    </aside>
  )
}
