import { renderHook, act } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useSurvey } from '../useSurvey'
import { useStore } from '../../store'

const mockState = vi.hoisted(() => ({
  capturedOnEvent: null as null | ((event: string, data: unknown) => void),
}))

vi.mock('../../api', () => ({
  startSurveySSE: vi.fn((_request, onEvent) => {
    mockState.capturedOnEvent = onEvent
    return vi.fn()
  }),
}))

const samplePersona = {
  uuid: 'persona-1',
  name: '田中太郎',
  age: 35,
  sex: '男',
  prefecture: '東京都',
  region: '関東',
  occupation: '会社員',
  education_level: '大学卒',
  marital_status: '既婚',
  persona: 'テスト用ペルソナ',
  professional_persona: '会社員',
  cultural_background: '日本',
  skills_and_expertise: '営業',
  hobbies_and_interests: '読書',
  career_goals_and_ambitions: '昇進',
}

describe('useSurvey', () => {
  afterEach(() => {
    mockState.capturedOnEvent = null
    useStore.getState().resetSurvey()
  })

  it('clears activeAnswer with undefined when persona_answer arrives', () => {
    useStore.setState({
      selectedPersonas: [samplePersona],
      surveyTheme: 'テストテーマ',
      questions: ['質問1'],
      surveyLabel: '',
      enableThinking: false,
    })

    const { result, unmount } = renderHook(() => useSurvey())

    act(() => {
      result.current.startSurvey()
    })

    act(() => {
      mockState.capturedOnEvent?.('persona_start', {
        persona_uuid: samplePersona.uuid,
        name: samplePersona.name,
        index: 0,
        total: 1,
      })
    })

    expect(useStore.getState().personaStates[samplePersona.uuid].activeAnswer).toBe('')

    act(() => {
      mockState.capturedOnEvent?.('persona_answer', {
        persona_uuid: samplePersona.uuid,
        question_index: 0,
        answer: '【評価: 4】回答本文',
        score: 4,
      })
    })

    expect(useStore.getState().personaStates[samplePersona.uuid].activeAnswer).toBeUndefined()
    expect(useStore.getState().personaStates[samplePersona.uuid].answers[0]).toMatchObject({
      question: '質問1',
      answer: '【評価: 4】回答本文',
      score: 4,
    })

    act(() => {
      result.current.cancelSurvey()
    })
    unmount()
  })
})
