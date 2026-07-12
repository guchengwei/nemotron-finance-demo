import { useCallback, useRef } from 'react'
import { useStore } from '../store'
import { api, startSurveySSE } from '../api'
import type {
  SSERunCreated,
  SSEQuestionsGenerated,
  SSEPersonaStart,
  SSEPersonaAnswerChunk,
  SSEPersonaAnswer,
  SSEPersonaThinking,
  SSEPersonaComplete,
  SSESurveyComplete,
} from '../types'

export function useSurvey() {
  const cancelRef = useRef<(() => void) | null>(null)
  const chunkBuffer = useRef<Record<string, string>>({})
  const flushRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const startingRef = useRef(false)
  const highestEventIdRef = useRef(0)

  const stopFlushLoop = () => {
    if (flushRef.current) {
      clearInterval(flushRef.current)
      flushRef.current = null
    }
  }

  const flushBufferedChunks = () => {
    const s = useStore.getState()
    for (const [pid, text] of Object.entries(chunkBuffer.current)) {
      const ps = s.personaStates[pid]
      if (ps && text) {
        s.updatePersonaState(pid, { activeAnswer: (ps.activeAnswer || '') + text })
      }
    }
    chunkBuffer.current = {}
  }

  const startSurvey = useCallback(() => {
    if (startingRef.current) return
    startingRef.current = true

    cancelRef.current?.()
    cancelRef.current = null
    stopFlushLoop()
    chunkBuffer.current = {}
    highestEventIdRef.current = 0

    const { selectedPersonas, surveyTheme, questions, surveyLabel, enableThinking, setPersonaStates, setSurveyComplete, setSurveyCounts, setCurrentHistoryRun, setCurrentReport } = useStore.getState()

    const initialStates = Object.fromEntries(
      selectedPersonas.map((p) => [p.uuid, { persona: p, status: 'waiting' as const, answers: [] }]),
    )
    setPersonaStates(initialStates)
    setCurrentHistoryRun(null)
    setCurrentReport(null)
    setSurveyComplete(false)
    setSurveyCounts(0, 0)

    flushRef.current = setInterval(() => {
      flushBufferedChunks()
    }, 100)

    const finishWithError = () => {
      const s = useStore.getState()
      stopFlushLoop()
      flushBufferedChunks()
      const completedCount = Object.values(s.personaStates).filter((ps) => ps.status === 'complete').length
      const failedCount = Math.max(1, Object.values(s.personaStates).filter((ps) => ps.status === 'error').length)
      s.setSurveyComplete(true)
      s.setSurveyCounts(completedCount, failedCount)
      cancelRef.current = null
      startingRef.current = false
    }

    const cancel = startSurveySSE(
      {
        persona_ids: selectedPersonas.map((p) => p.uuid),
        survey_theme: surveyTheme,
        questions,
        label: surveyLabel || undefined,
        enable_thinking: enableThinking,
      },
      (event, data, eventId?: number) => {
        if (eventId !== undefined) {
          if (eventId <= highestEventIdRef.current) return
          highestEventIdRef.current = eventId
        }
        const s = useStore.getState()
        switch (event) {
          case 'run_created': {
            const d = data as SSERunCreated
            s.setCurrentRunId(d.run_id)
            startingRef.current = false
            break
          }
          case 'questions_generated': {
            const d = data as SSEQuestionsGenerated
            s.setQuestions(d.questions)
            break
          }
          case 'persona_start': {
            const d = data as SSEPersonaStart
            s.updatePersonaState(d.persona_uuid, { status: 'active', activeAnswer: '', activeQuestion: 0 })
            break
          }
          case 'persona_thinking': {
            const d = data as SSEPersonaThinking
            s.updatePersonaState(d.persona_uuid, { activeThinking: d.thinking, activeQuestion: d.question_index })
            break
          }
          case 'persona_answer_chunk': {
            const d = data as SSEPersonaAnswerChunk
            chunkBuffer.current[d.persona_uuid] = (chunkBuffer.current[d.persona_uuid] || '') + d.chunk
            const ps = s.personaStates[d.persona_uuid]
            if (ps && ps.activeQuestion !== d.question_index) {
              s.updatePersonaState(d.persona_uuid, { activeQuestion: d.question_index })
            }
            break
          }
          case 'persona_answer': {
            const d = data as SSEPersonaAnswer
            const buffered = chunkBuffer.current[d.persona_uuid] || ''
            delete chunkBuffer.current[d.persona_uuid]
            const ps = s.personaStates[d.persona_uuid]
            if (ps) {
              const newAnswers = [...ps.answers]
              const q = s.questions[d.question_index] || `Q${d.question_index + 1}`
              newAnswers[d.question_index] = {
                question: q,
                answer: d.answer || buffered,
                score: d.score || undefined,
                thinking: d.thinking || undefined,
              }
              s.updatePersonaState(d.persona_uuid, {
                answers: newAnswers,
                activeAnswer: undefined,
                activeThinking: undefined,
                activeQuestion: undefined,
              })
            }
            break
          }
          case 'persona_complete': {
            const d = data as SSEPersonaComplete
            s.updatePersonaState(d.persona_uuid, { status: 'complete', activeAnswer: '' })
            const updated = useStore.getState().personaStates
            const completedCount = Object.values(updated).filter((ps) => ps.status === 'complete').length
            const failedCount = Object.values(updated).filter((ps) => ps.status === 'error').length
            s.setSurveyCounts(completedCount, failedCount)
            break
          }
          case 'persona_error': {
            const d = data as { persona_uuid: string; question_index?: number; scope?: string; message?: string }
            if (d.scope === 'question' && d.question_index !== undefined) {
              const ps = s.personaStates[d.persona_uuid]
              if (ps) {
                const newAnswers = [...ps.answers]
                newAnswers[d.question_index] = {
                  question: s.questions[d.question_index] || `Q${d.question_index + 1}`,
                  answer: d.message || '回答を取得できませんでした。',
                  failed: true,
                }
                s.updatePersonaState(d.persona_uuid, { answers: newAnswers, activeAnswer: undefined })
              }
              break
            }
            s.updatePersonaState(d.persona_uuid, { status: 'error', activeAnswer: '', activeThinking: undefined })
            const updated = useStore.getState().personaStates
            const completedCount = Object.values(updated).filter((ps) => ps.status === 'complete').length
            const failedCount = Object.values(updated).filter((ps) => ps.status === 'error').length
            s.setSurveyCounts(completedCount, failedCount)
            break
          }
          case 'survey_complete': {
            const d = data as SSESurveyComplete
            stopFlushLoop()
            flushBufferedChunks()
            s.setSurveyComplete(true)
            s.setSurveyCounts(d.completed, d.failed)
            cancelRef.current = null
            startingRef.current = false
            break
          }
          case 'survey_error': {
            for (const [personaId, state] of Object.entries(s.personaStates)) {
              if (state.status === 'waiting' || state.status === 'active') {
                s.updatePersonaState(personaId, { status: 'not_completed', activeAnswer: undefined })
              }
            }
            finishWithError()
            break
          }
          case 'survey_cancelled': {
            stopFlushLoop()
            for (const [personaId, state] of Object.entries(s.personaStates)) {
              if (state.status === 'waiting' || state.status === 'active') {
                s.updatePersonaState(personaId, { status: 'not_completed', activeAnswer: undefined })
              }
            }
            const d = data as SSESurveyComplete
            s.setSurveyComplete(true)
            s.setSurveyCounts(d.completed, d.failed)
            cancelRef.current = null
            startingRef.current = false
            break
          }
        }
      },
      (err) => {
        console.error('Survey SSE error:', err)
        if (err.message === 'Survey observer disconnected') return
        finishWithError()
      },
      (state) => useStore.getState().setConnectionState(state),
    )

    cancelRef.current = cancel
  }, [])

  const cancelSurvey = useCallback(() => {
    const runId = useStore.getState().currentRunId
    if (!runId) return
    api.cancelSurvey(runId).catch((error) => {
      console.error('Survey cancellation failed:', error)
    })
  }, [])

  return { startSurvey, cancelSurvey }
}
