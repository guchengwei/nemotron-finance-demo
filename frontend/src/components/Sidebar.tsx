import { useEffect, useState } from 'react'
import { useStore } from '../store'
import { api } from '../api'
import type { Persona, PersonaRunState, SurveyRunDetail } from '../types'

function scoreColor(score?: number): string {
  if (!score) return 'bg-fin-panel text-fin-muted'
  if (score >= 4.5) return 'bg-fin-accent text-fin-surface'
  if (score >= 3.5) return 'bg-fin-success text-fin-surface'
  if (score >= 2.5) return 'bg-fin-warning text-fin-surface'
  return 'bg-fin-danger text-fin-surface'
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
  const { history, setHistory, setStep, setCurrentReport, setCurrentHistoryRun, resetSurvey, setSelectedPersonas, setQuestions, setSurveyTheme, setSurveyLabel, setCurrentRunId, setPersonaStates, setSurveyComplete, setSurveyCounts, setEnableThinking } = useStore()
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

      if (detail.status === 'completed') {
        const reconstructed = buildPersonaStates(detail)
        setSelectedPersonas(reconstructed.personas)
        setPersonaStates(reconstructed.personaStates)
        setSurveyCounts(reconstructed.completed, reconstructed.failed)
        setSurveyComplete(true)
        setEnableThinking(detail.enable_thinking ?? true)
        setStep(4)
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
    <aside className="flex h-full w-64 flex-shrink-0 flex-col border-r border-fin-border/90 bg-fin-surface/95 backdrop-blur">
      <div className="border-b border-fin-border/80 px-5 py-5">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-2xl bg-fin-accent text-xs font-black text-fin-surface shadow-card">
            <span>N</span>
          </div>
          <div>
            <div className="text-xs font-bold tracking-[0.2em] text-fin-accent">NEMOTRON</div>
            <div className="text-[10px] text-fin-muted">Financial Survey</div>
          </div>
        </div>
      </div>

      <div className="p-4">
        <button
          data-testid="new-survey-button"
          disabled={!dbReady}
          onClick={() => resetSurvey()}
          className={`w-full rounded-full bg-fin-accent px-4 py-3 text-sm font-semibold text-fin-surface transition-all duration-200 hover:-translate-y-0.5 hover:bg-fin-accentStrong ${!dbReady ? 'cursor-not-allowed opacity-50' : ''}`}
        >
          ＋ 新規調査
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="px-4 py-2 text-[10px] font-semibold uppercase tracking-[0.22em] text-fin-muted">
          調査履歴
        </div>
        {history.length === 0 ? (
          <div className="px-4 py-6 text-center text-xs text-fin-muted">
            履歴はありません
          </div>
        ) : (
          history.map((run) => (
            <button
              key={run.id}
              data-testid={`history-run-${run.id}`}
              onClick={() => loadRun(run.id)}
              className="group relative mx-3 mb-2 w-[calc(100%-1.5rem)] rounded-2xl border border-transparent bg-fin-surface px-4 py-3 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-fin-border hover:bg-fin-panel/60"
            >
              <div className="mb-2 flex items-center justify-between">
                <span
                  data-testid={`history-run-status-${run.id}`}
                  className={`rounded-full px-2 py-1 text-[10px] font-bold ${scoreColor(run.overall_score)}`}
                >
                  {run.overall_score ? `${run.overall_score}★` : run.status === 'running' ? '実行中' : '—'}
                </span>
                <span className="text-[10px] tabular-nums text-fin-muted">
                  {run.persona_count}名
                </span>
              </div>
              <div className="line-clamp-2 text-xs text-fin-ink transition-colors group-hover:text-fin-accentStrong">
                {run.label || run.survey_theme}
              </div>
              <div className="mt-1 text-[10px] tabular-nums text-fin-muted">
                {new Date(run.created_at).toLocaleDateString('ja-JP')}
              </div>
              <div
                data-testid={`delete-run-${run.id}`}
                role="button"
                onClick={(e) => deleteRun(e, run.id)}
                className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full text-xs text-fin-muted opacity-0 transition-all hover:bg-fin-danger/10 hover:text-fin-danger group-hover:opacity-100"
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
