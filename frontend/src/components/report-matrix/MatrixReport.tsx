import { useEffect, useRef } from 'react'
import { useStore } from '../../store'
import { startMatrixReportSSE } from '../../api'
import type { AxisConfig, ScoredPersona, KeywordSummary, Recommendation, ScoreTableRow, AggregatedKeyword } from '../../types/matrix-report'
import QuadrantMatrix from './QuadrantMatrix'
import KeywordPanel from './KeywordPanel'
import RecommendationCards from './RecommendationCards'
import ScoreTable from './ScoreTable'

interface MatrixReportProps {
  surveyId: string
}

export default function MatrixReport({ surveyId }: MatrixReportProps) {
  const matrixReport = useStore((s) => s.matrixReport)
  const setMatrixReport = useStore((s) => s.setMatrixReport)
  const selectedPersonas = useStore((s) => s.selectedPersonas)
  const currentHistoryRun = useStore((s) => s.currentHistoryRun)
  const openPersonaDetail = useStore((s) => s.openPersonaDetail)
  const abortRef = useRef<(() => void) | null>(null)

  function resolvePersona(personaId: string) {
    const fromSelected = selectedPersonas.find((p) => p.uuid === personaId)
    if (fromSelected) return fromSelected
    if (currentHistoryRun) {
      const answer = currentHistoryRun.answers.find((a) => a.persona_uuid === personaId)
      if (answer?.persona_full_json) {
        try {
          return JSON.parse(answer.persona_full_json) as import('../../types').Persona
        } catch {
          /* skip malformed stored JSON */
        }
      }
    }
    return null
  }

  function handlePersonaClick(scoredPersona: ScoredPersona) {
    const persona = resolvePersona(scoredPersona.persona_id)
    if (persona) {
      openPersonaDetail(persona)
    }
  }

  useEffect(() => {
    if (!surveyId) return
    // Reset state
    setMatrixReport({ status: 'streaming', axes: null, personas: [], keywords: null, recommendations: [], scoreTable: [], errorMessage: '' })

    const abort = startMatrixReportSSE(
      { survey_id: surveyId, preset_key: 'interest_barrier' },
      (event, data) => {
        if (event === 'axis_ready') {
          setMatrixReport({ axes: data as AxisConfig })
        } else if (event === 'persona_scored') {
          // Append to personas using functional update pattern
          const p = data as ScoredPersona
          useStore.setState((s) => ({
            matrixReport: { ...s.matrixReport, personas: [...s.matrixReport.personas, p] }
          }))
        } else if (event === 'keywords_ready') {
          setMatrixReport({ keywords: data as KeywordSummary })
        } else if (event === 'recommendations_ready') {
          setMatrixReport({ recommendations: data as Recommendation[] })
        } else if (event === 'score_table_ready') {
          setMatrixReport({ scoreTable: data as ScoreTableRow[] })
        } else if (event === 'keyword_elaborated') {
          const { keyword_text, elaboration } = data as { keyword_text: string; elaboration: string }
          useStore.setState((s) => {
            const kw = s.matrixReport.keywords
            if (!kw) return s
            const update = (list: AggregatedKeyword[]) =>
              list.map((k) => k.text === keyword_text ? { ...k, elaboration } : k)
            return {
              matrixReport: {
                ...s.matrixReport,
                keywords: { strengths: update(kw.strengths), weaknesses: update(kw.weaknesses) },
              },
            }
          })
        } else if (event === 'report_complete') {
          setMatrixReport({ status: 'complete' })
        } else if (event === 'report_error') {
          setMatrixReport({ status: 'error', errorMessage: (data as { error: string }).error })
        }
      },
      (err) => {
        setMatrixReport({ status: 'error', errorMessage: err.message })
      },
    )

    abortRef.current = abort
    return () => { abortRef.current?.() }
  }, [surveyId])

  const { axes, personas, keywords, recommendations, scoreTable, status, errorMessage } = matrixReport

  if (status === 'error') {
    return <div className="p-6 text-center text-sm text-fin-danger">{errorMessage || 'エラーが発生しました'}</div>
  }

  if (!axes && status === 'streaming') {
    return <div className="p-6 text-center text-sm text-fin-muted animate-pulse">分析を準備中...</div>
  }

  return (
    <div className="space-y-6">
      {axes && (
        <QuadrantMatrix axes={axes} personas={personas} onPersonaClick={handlePersonaClick} />
      )}

      {keywords && (
        <div>
          <h3 className="mb-3 text-sm font-bold text-fin-ink">キーワード分析</h3>
          <KeywordPanel keywords={keywords} />
        </div>
      )}

      <div>
        <h3 className="mb-3 text-sm font-bold text-fin-ink">提案</h3>
        <RecommendationCards recommendations={recommendations} />
      </div>

      {scoreTable.length > 0 && axes && (
        <div>
          <h3 className="mb-3 text-sm font-bold text-fin-ink">回答者スコア一覧</h3>
          <ScoreTable rows={scoreTable} axes={axes} onRowClick={(row) => handlePersonaClick({ ...row, keywords: [] })} />
        </div>
      )}

      {status === 'streaming' && (
        <p className="text-center text-xs text-fin-muted animate-pulse">分析中...</p>
      )}
    </div>
  )
}
