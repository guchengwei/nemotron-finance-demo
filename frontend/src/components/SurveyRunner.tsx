import React, { useEffect, useRef } from 'react'
import { useStore } from '../store'
import { api } from '../api'
import PersonaAvatar from './PersonaAvatar'
import SurveyProgress from './SurveyProgress'
import { scoreBg } from '../utils/scoreParser'

const LARGE_SURVEY_THRESHOLD = 30

function ThinkingBlock({ thinking }: { thinking: string }) {
  return (
    <details data-testid="survey-thinking-block" className="mt-1.5 group">
      <summary className="text-[10px] text-gray-600 cursor-pointer select-none list-none flex items-center gap-1 hover:text-gray-500 transition-colors w-fit">
        <span className="transition-transform group-open:rotate-90 inline-block">▸</span>
        <span>思考過程</span>
      </summary>
      <div className="mt-1 text-xs text-slate-300 bg-[#0F172A] rounded p-2 whitespace-pre-wrap font-mono leading-relaxed max-h-40 overflow-y-auto border border-[rgba(148,163,184,0.18)]">
        {thinking}
      </div>
    </details>
  )
}

const PersonaListItem = React.memo(function PersonaListItem({
  name,
  age,
  sex,
  status,
  score,
  isActive,
  onClick,
}: {
  name: string
  age: number
  sex: string
  status: string
  score?: number
  isActive: boolean
  onClick: () => void
}) {
  const statusIcon = status === 'complete' ? '✓' : status === 'error' ? '✗' : status === 'active' ? '●' : '○'
  const statusColor = status === 'complete' ? 'text-green-400' : status === 'error' ? 'text-red-400' : status === 'active' ? 'text-[#2563EB]' : 'text-gray-600'

  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2 flex items-center gap-2 rounded transition-colors ${isActive ? 'bg-[#2563EB]/10 border border-[rgba(37,99,235,0.3)]' : 'hover:bg-[#1E2D40]'}`}
    >
      <span className={`text-xs ${statusColor} ${status === 'active' ? 'pulse-green' : ''}`}>
        {statusIcon}
      </span>
      <PersonaAvatar name={name} age={age} sex={sex} size={24} />
      <div className="flex-1 min-w-0">
        <div className="text-xs text-gray-300 truncate">{name}</div>
      </div>
      {score !== undefined && (
        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded text-white ${scoreBg(score)}`}>
          {score}
        </span>
      )}
    </button>
  )
})

export default function SurveyRunner() {
  const {
    personaStates, surveyComplete, surveyCompleted, surveyFailed,
    questions, currentRunId, setCurrentReport, setStep, selectedPersonas, currentHistoryRun,
  } = useStore()

  const feedRef = useRef<HTMLDivElement>(null)

  const total = selectedPersonas.length
  const isLarge = total > LARGE_SURVEY_THRESHOLD
  const restoredInterruptedRun = currentHistoryRun?.status === 'running'
  const restoredFailedRun = currentHistoryRun?.status === 'failed'

  const allStates = Object.values(personaStates)
  const activePersona = allStates.find((s) => s.status === 'active')
  const activeUuid = activePersona?.persona.uuid || null

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: 'smooth' })
  }, [activePersona?.activeAnswer, activePersona?.answers.length])

  const scores = allStates.flatMap((s) =>
    s.answers.filter((a) => a.score !== undefined).map((a) => a.score!),
  )
  const avgScore = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : undefined

  useEffect(() => {
    if (!surveyComplete || !currentRunId || surveyFailed > 0) return
    const hasAnswers = Object.values(personaStates).some((s) => s.answers.length > 0)
    if (!hasAnswers) return

    const timer = setTimeout(async () => {
      try {
        const report = await api.generateReport(currentRunId)
        setCurrentReport(report)
        setStep(4)
      } catch (e) {
        console.error('Report generation failed:', e)
      }
    }, 1500)
    return () => clearTimeout(timer)
  }, [surveyComplete, currentRunId, personaStates, setCurrentReport, setStep, surveyFailed])

  const completed = allStates.filter((s) => s.status === 'complete')
  const errored = allStates.filter((s) => s.status === 'error')
  const displayUuid = activeUuid || (errored[0]?.persona.uuid ?? completed[completed.length - 1]?.persona.uuid)
  const displayState = displayUuid ? personaStates[displayUuid] : null

  const headerLabel = surveyComplete
    ? surveyFailed > 0 && surveyCompleted === 0
      ? '調査エラー'
      : surveyFailed > 0
        ? '一部失敗して完了'
        : '✓ 調査完了'
    : restoredInterruptedRun
      ? '調査が中断されました'
      : restoredFailedRun
        ? '調査エラー'
        : '調査実行中...'

  return (
    <div data-testid="survey-runner-screen" className="h-full flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-white">{headerLabel}</h2>
        <div className="flex gap-2">
          {(surveyComplete || restoredInterruptedRun || restoredFailedRun) && (surveyCompleted > 0 || allStates.some((s) => s.answers.length > 0)) && (
            <button
              onClick={async () => {
                if (currentRunId) {
                  try {
                    const report = await api.generateReport(currentRunId)
                    setCurrentReport(report)
                  } catch (e) {
                    console.error('Report generation failed:', e)
                  }
                }
                setStep(4)
              }}
              className="bg-[#2563EB] text-black font-bold px-4 py-2 rounded text-sm"
            >
              レポートを見る →
            </button>
          )}
        </div>
      </div>

      {(restoredInterruptedRun || restoredFailedRun || (surveyComplete && surveyFailed > 0)) && (
        <div
          data-testid="survey-interruption-banner"
          className="rounded-lg border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100"
        >
          {restoredInterruptedRun
            ? 'この調査は途中で停止しました。ここでは途中経過を確認できます。'
            : '一部の回答でエラーが発生しました。途中までの結果を確認できます。'}
        </div>
      )}

      <SurveyProgress
        completed={surveyCompleted}
        total={total}
        failed={surveyFailed}
        averageScore={avgScore}
      />

      <div className="flex-1 flex gap-4 min-h-0">
        <div className="w-44 flex-shrink-0 bg-[#1E293B] rounded-lg overflow-y-auto">
          <div className="px-3 py-2 text-[10px] text-gray-600 uppercase tracking-wider border-b border-[rgba(255,255,255,0.05)]">
            ペルソナ一覧
          </div>
          {selectedPersonas.map((p) => {
            const state = personaStates[p.uuid]
            const firstScore = state?.answers.find((a) => a.score !== undefined)?.score
            return (
              <PersonaListItem
                key={p.uuid}
                name={p.name}
                age={p.age}
                sex={p.sex}
                status={state?.status || 'waiting'}
                score={firstScore}
                isActive={p.uuid === displayUuid}
                onClick={() => {}}
              />
            )
          })}
        </div>

        <div className="flex-1 bg-[#1E293B] rounded-lg flex flex-col overflow-hidden">
          {displayState ? (
            <>
              <div className="flex items-center gap-3 px-4 py-3 border-b border-[rgba(255,255,255,0.05)]">
                <PersonaAvatar
                  name={displayState.persona.name}
                  age={displayState.persona.age}
                  sex={displayState.persona.sex}
                  size={36}
                />
                <div>
                  <div className="text-sm font-bold text-white">{displayState.persona.name}</div>
                  <div className="text-xs text-gray-500">
                    {displayState.persona.age}歳 · {displayState.persona.occupation} · {displayState.persona.prefecture}
                  </div>
                </div>
                {displayState.status === 'active' && (
                  <div className="ml-auto text-xs text-[#2563EB] pulse-green">回答中...</div>
                )}
              </div>

              <div ref={feedRef} className="flex-1 overflow-y-auto p-4 space-y-4">
                {displayState.answers.map((ans, i) => (
                  <div key={i} className="fade-in">
                    <div className="text-xs text-gray-500 mb-1">Q{i + 1}: {ans.question}</div>
                    {ans.thinking && <ThinkingBlock thinking={ans.thinking} />}
                    <div
                      data-testid="survey-answer-block"
                      className="bg-[#1E2D40] rounded-lg p-3 text-sm text-gray-100 border border-[rgba(37,99,235,0.12)]"
                    >
                      {ans.score !== undefined && (
                        <span className={`inline-block text-xs font-bold px-2 py-0.5 rounded mr-2 text-white ${scoreBg(ans.score)}`}>
                          {ans.score}
                        </span>
                      )}
                      {ans.answer}
                    </div>
                  </div>
                ))}

                {displayState.status === 'error' && (
                  <div className="text-sm text-red-300 bg-red-900/20 rounded-lg p-3 border border-red-500/20">
                    このペルソナの回答は途中で停止しました。
                  </div>
                )}

                {displayState.status === 'active' && displayState.activeAnswer !== undefined && (
                  <div className="fade-in">
                    <div className="text-xs text-gray-500 mb-1">
                      Q{(displayState.activeQuestion ?? 0) + 1}: {questions[displayState.activeQuestion ?? 0]}
                    </div>
                    {displayState.activeThinking && (
                      <ThinkingBlock thinking={displayState.activeThinking} />
                    )}
                    <div
                      data-testid="survey-active-answer-block"
                      className="bg-[#F8FAFC] text-slate-900 border border-[rgba(37,99,235,0.25)] rounded-lg p-3 text-sm mt-1"
                    >
                      {isLarge ? (
                        <span>{displayState.activeAnswer || <span className="text-slate-500">回答中...</span>}</span>
                      ) : (
                        <span className={displayState.activeAnswer ? 'cursor-blink' : 'text-slate-500'}>
                          {displayState.activeAnswer || '入力中...'}
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-full text-sm text-gray-500">
              表示できる回答がまだありません
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
