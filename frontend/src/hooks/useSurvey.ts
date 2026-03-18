import { useCallback, useRef } from 'react'
import { useStore } from '../store'
import { startSurveySSE } from '../api'
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
  const store = useStore()
  const cancelRef = useRef<(() => void) | null>(null)
  const chunkBuffer = useRef<Record<string, string>>({})
  const flushRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const startSurvey = useCallback(() => {
    const { selectedPersonas, surveyTheme, questions, surveyLabel } = useStore.getState()

    // Reset persona states
    const initialStates: typeof store.personaStates = {}
    for (const p of selectedPersonas) {
      initialStates[p.uuid] = {
        persona: p,
        status: 'waiting',
        answers: [],
      }
    }
    store.setPersonaState = store.setPersonaState  // reference
    for (const [uuid, state] of Object.entries(initialStates)) {
      store.setPersonaState(uuid, state)
    }
    store.setSurveyComplete(false)
    store.setSurveyCounts(0, 0)

    // Start batched flush for chunks
    if (flushRef.current) clearInterval(flushRef.current)
    flushRef.current = setInterval(() => {
      const buf = chunkBuffer.current
      const keys = Object.keys(buf)
      if (keys.length === 0) return
      const s = useStore.getState()
      for (const pid of keys) {
        const ps = s.personaStates[pid]
        if (ps) {
          const current = ps.activeAnswer || ''
          s.updatePersonaState(pid, { activeAnswer: current + buf[pid] })
        }
      }
      chunkBuffer.current = {}
    }, 100)

    const cancel = startSurveySSE(
      {
        persona_ids: selectedPersonas.map((p) => p.uuid),
        survey_theme: surveyTheme,
        questions,
        label: surveyLabel || undefined,
      },
      (event, data) => {
        const s = useStore.getState()
        switch (event) {
          case 'run_created': {
            const d = data as SSERunCreated
            s.setCurrentRunId(d.run_id)
            break
          }
          case 'questions_generated': {
            const d = data as SSEQuestionsGenerated
            s.setQuestions(d.questions)
            break
          }
          case 'persona_start': {
            const d = data as SSEPersonaStart
            s.updatePersonaState(d.persona_uuid, { status: 'active', activeAnswer: '' })
            break
          }
          case 'persona_thinking': {
            const d = data as SSEPersonaThinking
            s.updatePersonaState(d.persona_uuid, { activeThinking: d.thinking })
            break
          }
          case 'persona_answer_chunk': {
            const d = data as SSEPersonaAnswerChunk
            // Buffer chunks instead of immediate store update
            chunkBuffer.current[d.persona_uuid] = (chunkBuffer.current[d.persona_uuid] || '') + d.chunk
            // Still update activeQuestion immediately (it's cheap)
            const ps = s.personaStates[d.persona_uuid]
            if (ps && ps.activeQuestion !== d.question_index) {
              s.updatePersonaState(d.persona_uuid, { activeQuestion: d.question_index })
            }
            break
          }
          case 'persona_answer': {
            const d = data as SSEPersonaAnswer
            // Flush any buffered chunks for this persona
            delete chunkBuffer.current[d.persona_uuid]
            const ps = s.personaStates[d.persona_uuid]
            if (ps) {
              const newAnswers = [...ps.answers]
              const q = s.questions[d.question_index] || `Q${d.question_index + 1}`
              newAnswers[d.question_index] = {
                question: q,
                answer: d.answer,
                score: d.score || undefined,
                thinking: d.thinking || undefined,
              }
              s.updatePersonaState(d.persona_uuid, {
                answers: newAnswers,
                activeAnswer: '',
                activeThinking: undefined,
                activeQuestion: undefined,
              })
            }
            break
          }
          case 'persona_complete': {
            const d = data as SSEPersonaComplete
            s.updatePersonaState(d.persona_uuid, { status: 'complete', activeAnswer: '' })
            break
          }
          case 'persona_error': {
            const d = data as { persona_uuid: string }
            s.updatePersonaState(d.persona_uuid, { status: 'error' })
            break
          }
          case 'survey_complete': {
            const d = data as SSESurveyComplete
            // Flush any remaining chunks
            if (flushRef.current) {
              clearInterval(flushRef.current)
              flushRef.current = null
            }
            const buf = chunkBuffer.current
            for (const [pid, text] of Object.entries(buf)) {
              const ps2 = s.personaStates[pid]
              if (ps2) s.updatePersonaState(pid, { activeAnswer: (ps2.activeAnswer || '') + text })
            }
            chunkBuffer.current = {}
            s.setSurveyComplete(true)
            s.setSurveyCounts(d.completed, d.failed)
            cancelRef.current = null
            break
          }
        }
      },
      (err) => {
        console.error('Survey SSE error:', err)
      }
    )

    cancelRef.current = cancel
  }, [])

  const cancelSurvey = useCallback(() => {
    cancelRef.current?.()
    cancelRef.current = null
    if (flushRef.current) {
      clearInterval(flushRef.current)
      flushRef.current = null
    }
    chunkBuffer.current = {}
  }, [])

  return { startSurvey, cancelSurvey }
}
