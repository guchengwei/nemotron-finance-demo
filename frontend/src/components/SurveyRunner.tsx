import { useEffect, useRef } from 'react'
import { useStore } from '../store'
import { api } from '../api'
import PersonaAvatar from './PersonaAvatar'
import SurveyProgress from './SurveyProgress'
import { scoreBg } from '../utils/scoreParser'

const LARGE_SURVEY_THRESHOLD = 30

function ThinkingBlock({ thinking }: { thinking: string }) {
  return (
    <details className="mt-1.5 group">
      <summary className="text-[10px] text-gray-600 cursor-pointer select-none list-none flex items-center gap-1 hover:text-gray-500 transition-colors w-fit">
        <span className="transition-transform group-open:rotate-90 inline-block">▸</span>
        <span>思考過程</span>
      </summary>
      <div className="mt-1 text-xs text-gray-600 bg-[#0a0a0f] rounded p-2 whitespace-pre-wrap font-mono leading-relaxed max-h-40 overflow-y-auto">
        {thinking}
      </div>
    </details>
  )
}

function PersonaListItem({
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
  const statusColor = status === 'complete' ? 'text-green-400' : status === 'error' ? 'text-red-400' : status === 'active' ? 'text-[#76B900]' : 'text-gray-600'

  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2 flex items-center gap-2 rounded transition-colors
        ${isActive ? 'bg-[#76B900]/10 border border-[rgba(118,185,0,0.3)]' : 'hover:bg-[#1c1c2e]'}`}
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
}

export default function SurveyRunner() {
  const {
    personaStates, surveyComplete, surveyCompleted, surveyFailed,
    questions, currentRunId, setCurrentReport, setStep, selectedPersonas
  } = useStore()

  const feedRef = useRef<HTMLDivElement>(null)
  const activePersonaRef = useRef<string | null>(null)

  const total = selectedPersonas.length
  const isLarge = total > LARGE_SURVEY_THRESHOLD

  // Find active persona (currently answering)
  const allStates = Object.values(personaStates)
  const activePersona = allStates.find((s) => s.status === 'active')
  const activeUuid = activePersona?.persona.uuid || null

  // When active persona changes, update ref
  useEffect(() => {
    activePersonaRef.current = activeUuid
  }, [activeUuid])

  // Auto-scroll feed
  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: 'smooth' })
  }, [activePersona?.activeAnswer, activePersona?.answers.length])

  // Calculate average score
  const scores = allStates.flatMap((s) =>
    s.answers.filter((a) => a.score !== undefined).map((a) => a.score!)
  )
  const avgScore = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : undefined

  // Auto-advance to report when complete
  useEffect(() => {
    if (surveyComplete && currentRunId) {
      const timer = setTimeout(async () => {
        try {
          const report = await api.generateReport(currentRunId)
          setCurrentReport(report)
          setStep(4)
        } catch (e) {
          console.error('Report generation failed:', e)
          setStep(4)
        }
      }, 1500)
      return () => clearTimeout(timer)
    }
  }, [surveyComplete, currentRunId, setCurrentReport, setStep])

  // Display target: active persona, or last completed
  const completed = allStates.filter((s) => s.status === 'complete')
  const displayUuid = activeUuid || (completed.length > 0 ? completed[completed.length - 1].persona.uuid : undefined)
  const displayState = displayUuid ? personaStates[displayUuid] : null

  return (
    <div data-testid="survey-runner-screen" className="h-full flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-white">
          {surveyComplete ? '✓ 調査完了' : '調査実行中...'}
        </h2>
        {surveyComplete && (
          <button
            onClick={async () => {
              if (currentRunId) {
                const report = await api.generateReport(currentRunId)
                setCurrentReport(report)
              }
              setStep(4)
            }}
            className="bg-[#76B900] text-black font-bold px-4 py-2 rounded text-sm"
          >
            レポートを見る →
          </button>
        )}
      </div>

      {/* Progress */}
      <SurveyProgress
        completed={surveyCompleted}
        total={total}
        failed={surveyFailed}
        averageScore={avgScore}
      />

      {/* Main split view */}
      <div className="flex-1 flex gap-4 min-h-0">
        {/* Left: persona list */}
        <div className="w-44 flex-shrink-0 bg-[#141420] rounded-lg overflow-y-auto">
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

        {/* Right: live Q&A feed */}
        <div className="flex-1 bg-[#141420] rounded-lg flex flex-col overflow-hidden">
          {displayState ? (
            <>
              {/* Persona header */}
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
                  <div className="ml-auto text-xs text-[#76B900] pulse-green">回答中...</div>
                )}
              </div>

              {/* Q&A feed */}
              <div ref={feedRef} className="flex-1 overflow-y-auto p-4 space-y-4">
                {displayState.answers.map((ans, i) => (
                  <div key={i} className="fade-in">
                    <div className="text-xs text-gray-500 mb-1">Q{i + 1}: {ans.question}</div>
                    <div className="bg-[#1c1c2e] rounded-lg p-3 text-sm text-gray-200">
                      {ans.score !== undefined && (
                        <span className={`inline-block text-xs font-bold px-2 py-0.5 rounded mr-2 text-white ${scoreBg(ans.score)}`}>
                          {ans.score}
                        </span>
                      )}
                      {ans.answer}
                    </div>
                    {ans.thinking && <ThinkingBlock thinking={ans.thinking} />}
                  </div>
                ))}

                {/* Active streaming answer */}
                {displayState.status === 'active' && displayState.activeAnswer !== undefined && (
                  <div className="fade-in">
                    <div className="text-xs text-gray-500 mb-1">
                      Q{(displayState.activeQuestion ?? 0) + 1}: {questions[displayState.activeQuestion ?? 0]}
                    </div>
                    {displayState.activeThinking && (
                      <ThinkingBlock thinking={displayState.activeThinking} />
                    )}
                    <div className="bg-[#1c1c2e] border border-[rgba(118,185,0,0.2)] rounded-lg p-3 text-sm text-gray-200 mt-1">
                      {isLarge ? (
                        displayState.activeAnswer || <span className="text-gray-600">回答中...</span>
                      ) : (
                        <span className={displayState.activeAnswer ? 'cursor-blink' : 'text-gray-600'}>
                          {displayState.activeAnswer || '入力中...'}
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-600 text-sm">
              調査開始を待っています...
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
