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

    const { selectedPersonas, surveyTheme, questions, surveyLabel, enableThinking, setPersonaStates, setSurveyLifecycle, setSurveyCounts, setCurrentHistoryRun, setCurrentReport } = useStore.getState()

    const initialStates = Object.fromEntries(
      selectedPersonas.map((p) => [p.uuid, { persona: p, status: 'waiting' as const, answers: [] }]),
    )
    setPersonaStates(initialStates)
    setCurrentHistoryRun(null)
    setCurrentReport(null)
    setSurveyLifecycle('active')
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
      for (const [id, state] of Object.entries(s.personaStates)) {
        if (state.status === 'waiting' || state.status === 'active') {
          s.updatePersonaState(id, { status: 'not_completed', activeAnswer: undefined, activeThinking: undefined })
        }
      }
      s.setSurveyLifecycle('failed')
      s.setSurveyCounts(completedCount, failedCount)
      startingRef.current = false
    }

    let observerCancel: (() => void) | null = null
    let terminalReceived = false
    const closeTerminalObserver = () => {
      terminalReceived = true
      observerCancel?.()
      if (cancelRef.current === observerCancel) cancelRef.current = null
    }

    observerCancel = startSurveySSE(
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
          closeTerminalObserver()
          startingRef.current = false
          sessionStorage.removeItem('active-survey-run-id')
        }
      },
      (err) => {
        console.error('Survey SSE error:', err)
        if (err.message === 'Survey observer disconnected') return
        finishWithError()
        closeTerminalObserver()
      },
      (state) => useStore.getState().setConnectionState(state),
    )

    if (terminalReceived) {
      observerCancel()
    } else {
      cancelRef.current = observerCancel
    }
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
