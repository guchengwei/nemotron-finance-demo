import { useStore } from '../store'
import type { SurveyEventName } from '../api'

export type SurveyEventResult = 'none' | 'complete' | 'error' | 'cancelled'

export function applySurveyEvent(
  event: SurveyEventName,
  rawData: unknown,
  chunkBuffer?: Record<string, string>,
): SurveyEventResult {
  const data = rawData as Record<string, unknown>
  const store = useStore.getState()
  const personaId = data.persona_uuid as string | undefined

  if (event === 'run_created') store.setCurrentRunId(data.run_id as string)
  if (event === 'questions_generated') store.setQuestions(data.questions as string[])
  if (event === 'persona_start' && personaId) {
    store.updatePersonaState(personaId, { status: 'active', activeAnswer: '', activeQuestion: 0 })
  }
  if (event === 'persona_thinking' && personaId) {
    store.updatePersonaState(personaId, { activeThinking: data.thinking as string, activeQuestion: data.question_index as number })
  }
  if (event === 'persona_answer_chunk' && personaId) {
    if (chunkBuffer) {
      chunkBuffer[personaId] = `${chunkBuffer[personaId] || ''}${data.chunk || ''}`
      if (store.personaStates[personaId]?.activeQuestion !== data.question_index) {
        store.updatePersonaState(personaId, { activeQuestion: data.question_index as number })
      }
    } else {
      const state = store.personaStates[personaId]
      store.updatePersonaState(personaId, {
        activeQuestion: data.question_index as number,
        activeAnswer: `${state?.activeAnswer || ''}${data.chunk || ''}`,
      })
    }
  }
  if (event === 'persona_answer' && personaId) {
    const state = store.personaStates[personaId]
    if (state) {
      const answers = [...state.answers]
      const questionIndex = Number(data.question_index)
      answers[questionIndex] = {
        question: store.questions[questionIndex] || `Q${questionIndex + 1}`,
        answer: String(data.answer || chunkBuffer?.[personaId] || ''),
        score: data.score as number || undefined,
        thinking: data.thinking as string || undefined,
      }
      if (chunkBuffer) delete chunkBuffer[personaId]
      store.updatePersonaState(personaId, {
        answers, activeAnswer: undefined, activeThinking: undefined, activeQuestion: undefined,
      })
    }
  }
  if (event === 'persona_error' && personaId && data.scope === 'question') {
    const state = store.personaStates[personaId]
    if (state) {
      const answers = [...state.answers]
      const questionIndex = Number(data.question_index)
      answers[questionIndex] = {
        question: store.questions[questionIndex] || `Q${questionIndex + 1}`,
        answer: String(data.message || '回答を取得できませんでした。'), failed: true,
      }
      store.updatePersonaState(personaId, { answers, activeAnswer: undefined })
    }
  } else if (event === 'persona_error' && personaId) {
    store.updatePersonaState(personaId, { status: 'error', activeAnswer: undefined, activeThinking: undefined })
  }
  if (event === 'persona_complete' && personaId) {
    store.updatePersonaState(personaId, { status: 'complete', activeAnswer: '' })
  }
  if (event === 'persona_complete' || (event === 'persona_error' && data.scope !== 'question')) {
    const states = useStore.getState().personaStates
    store.setSurveyCounts(
      Object.values(states).filter((state) => state.status === 'complete').length,
      Object.values(states).filter((state) => state.status === 'error').length,
    )
  }
  if (event === 'survey_complete') {
    store.setSurveyComplete(true)
    store.setSurveyCounts(Number(data.completed || 0), Number(data.failed || 0))
    return 'complete'
  }
  if (event === 'survey_error' || event === 'survey_cancelled') {
    for (const [id, state] of Object.entries(store.personaStates)) {
      if (state.status === 'waiting' || state.status === 'active') {
        store.updatePersonaState(id, { status: 'not_completed', activeAnswer: undefined })
      }
    }
    store.setSurveyComplete(true)
    store.setSurveyCounts(Number(data.completed || 0), Number(data.failed || 0))
    return event === 'survey_error' ? 'error' : 'cancelled'
  }
  return 'none'
}
