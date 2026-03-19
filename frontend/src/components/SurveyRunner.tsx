import React, { useEffect, useRef } from 'react'
import { useStore } from '../store'
import { api } from '../api'
import PersonaAvatar from './PersonaAvatar'
import SurveyProgress from './SurveyProgress'
import { scoreBg } from '../utils/scoreParser'

function sanitizeVisibleText(text: string) {
  return text.replace(/<\/?think[^>]*>/gi, '').trim()
}

const LARGE_SURVEY_THRESHOLD = 30

function ThinkingBlock({ thinking }: { thinking: string }) {
  return (
    <details data-testid="survey-thinking-block" className="mt-1.5 group">
      <summary className="flex w-fit cursor-pointer list-none items-center gap-1 select-none text-[10px] text-fin-muted transition-colors hover:text-fin-accent">
        <span className="transition-transform group-open:rotate-90 inline-block">▸</span>
        <span>思考過程</span>
      </summary>
      <div className="mt-1 max-h-40 overflow-y-auto rounded-2xl border border-fin-border bg-fin-panel p-3 font-mono text-xs leading-relaxed text-fin-ink whitespace-pre-wrap">
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
  const statusColor = status === 'complete' ? 'text-fin-success' : status === 'error' ? 'text-fin-danger' : status === 'active' ? 'text-fin-accent' : 'text-fin-muted'

  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center gap-2 rounded-2xl border px-3 py-2 text-left transition-all duration-200 ${isActive ? 'border-fin-accent/40 bg-fin-accentSoft' : 'border-transparent hover:border-fin-border hover:bg-fin-panel/60'}`}
    >
      <span className={`text-xs ${statusColor} ${status === 'active' ? 'pulse-accent' : ''}`}>
        {statusIcon}
      </span>
      <PersonaAvatar name={name} age={age} sex={sex} size={24} />
      <div className="flex-1 min-w-0">
        <div className="truncate text-xs text-fin-ink">{name}</div>
      </div>
      {score !== undefined && (
        <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold text-fin-surface ${scoreBg(score)}`}>
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
    if (!surveyComplete || !currentRunId || surveyCompleted === 0) return
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
        <h2 className="text-lg font-bold tracking-[-0.03em] text-fin-ink">{headerLabel}</h2>
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
              className="rounded-full bg-fin-accent px-4 py-2 text-sm font-semibold text-fin-surface transition-all duration-200 hover:-translate-y-0.5 hover:bg-fin-accentStrong"
            >
              レポートを見る →
            </button>
          )}
        </div>
      </div>

      {(restoredInterruptedRun || restoredFailedRun || (surveyComplete && surveyFailed > 0)) && (
        <div
          data-testid="survey-interruption-banner"
          className="rounded-[1.5rem] border border-fin-warning/30 bg-fin-warning/10 px-4 py-3 text-sm text-fin-warning"
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

      <div className="flex min-h-0 flex-1 flex-col gap-4 xl:flex-row">
        <div className="h-44 flex-shrink-0 overflow-y-auto rounded-[1.5rem] border border-fin-border bg-fin-surface shadow-card xl:h-auto xl:w-44">
          <div className="border-b border-fin-border px-3 py-3 text-[10px] uppercase tracking-[0.2em] text-fin-muted">
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

        <div className="flex flex-1 flex-col overflow-hidden rounded-[1.75rem] border border-fin-border bg-fin-surface shadow-card">
          {displayState ? (
            <>
              <div className="flex items-center gap-3 border-b border-fin-border px-4 py-4">
                <PersonaAvatar
                  name={displayState.persona.name}
                  age={displayState.persona.age}
                  sex={displayState.persona.sex}
                  size={36}
                />
                <div>
                  <div className="text-sm font-bold text-fin-ink">{displayState.persona.name}</div>
                  <div className="text-xs text-fin-muted">
                    {displayState.persona.age}歳 · {displayState.persona.occupation} · {displayState.persona.prefecture}
                  </div>
                </div>
                {displayState.status === 'active' && (
                  <div className="ml-auto text-xs text-fin-accent pulse-accent">回答中...</div>
                )}
              </div>

              <div ref={feedRef} className="flex-1 overflow-y-auto p-4 space-y-4">
                {displayState.answers.map((ans, i) => (
                  <div key={i} className="fade-in">
                    <div className="mb-1 text-xs text-fin-muted">Q{i + 1}: {ans.question}</div>
                    {ans.thinking && <ThinkingBlock thinking={ans.thinking} />}
                    <div
                      data-testid="survey-answer-block"
                      className="rounded-[1.25rem] border border-fin-border bg-fin-panel p-3 text-sm text-fin-ink"
                    >
                      {ans.score !== undefined && (
                        <span className={`mr-2 inline-block rounded-full px-2 py-0.5 text-xs font-bold text-fin-surface ${scoreBg(ans.score)}`}>
                          {ans.score}
                        </span>
                      )}
                      {sanitizeVisibleText(ans.answer)}
                    </div>
                  </div>
                ))}

                {displayState.status === 'error' && (
                  <div className="rounded-[1.25rem] border border-fin-danger/25 bg-fin-danger/10 p-3 text-sm text-fin-danger">
                    このペルソナの回答は途中で停止しました。
                  </div>
                )}

                {displayState.status === 'active' && displayState.activeAnswer !== undefined && (
                  <div className="fade-in">
                    <div className="mb-1 text-xs text-fin-muted">
                      Q{(displayState.activeQuestion ?? 0) + 1}: {questions[displayState.activeQuestion ?? 0]}
                    </div>
                    {displayState.activeThinking && (
                      <ThinkingBlock thinking={displayState.activeThinking} />
                    )}
                    <div
                      data-testid="survey-active-answer-block"
                      className="mt-1 rounded-[1.25rem] border border-fin-accent/25 bg-fin-surface p-3 text-sm text-fin-ink shadow-card"
                    >
                      {isLarge ? (
                        <span>{sanitizeVisibleText(displayState.activeAnswer || '') || (
                          <span className="thinking-dots text-fin-accent">
                            <span>思考中</span><span>.</span><span>.</span><span>.</span>
                          </span>
                        )}</span>
                      ) : (
                        <span className={displayState.activeAnswer ? 'cursor-blink' : ''}>
                          {sanitizeVisibleText(displayState.activeAnswer || '') || (
                            <span className="thinking-dots text-fin-accent">
                              <span>思考中</span><span>.</span><span>.</span><span>.</span>
                            </span>
                          )}
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-fin-muted">
              表示できる回答がまだありません
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
