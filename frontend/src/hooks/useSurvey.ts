import { useCallback, useRef } from 'react'
import { useStore } from '../store'
import { api, startSurveySSE } from '../api'
import { applySurveyEvent } from './surveyEvents'

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
        const result = applySurveyEvent(event, data, chunkBuffer.current)
        if (event === 'run_created') startingRef.current = false
        if (result !== 'none') {
          stopFlushLoop()
          flushBufferedChunks()
          cancelRef.current = null
          startingRef.current = false
          sessionStorage.removeItem('active-survey-run-id')
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
