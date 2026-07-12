import { renderHook, act } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useSurvey } from '../useSurvey'
import { useStore } from '../../store'

const mockState = vi.hoisted(() => ({
  capturedOnEvent: null as null | ((event: string, data: unknown, id?: number) => void),
  cancelSurvey: vi.fn(),
  cancelObserver: vi.fn(),
  emitDuringStart: null as null | ((onEvent: (event: string, data: unknown, id?: number) => void) => void),
}))

vi.mock('../../api', () => ({
  api: { cancelSurvey: mockState.cancelSurvey },
  startSurveySSE: vi.fn((_request, onEvent) => {
    mockState.capturedOnEvent = onEvent
    mockState.emitDuringStart?.(onEvent)
    return mockState.cancelObserver
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
    mockState.emitDuringStart = null
    vi.clearAllMocks()
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

  it('ignores duplicate durable events and authoritative answers replace partial text', () => {
    useStore.setState({ selectedPersonas: [samplePersona], surveyTheme: 'theme', questions: ['質問1'] })
    const { result } = renderHook(() => useSurvey())
    act(() => result.current.startSurvey())
    act(() => {
      mockState.capturedOnEvent?.('persona_answer_chunk', {
        persona_uuid: samplePersona.uuid, question_index: 0, chunk: 'partial',
      })
      mockState.capturedOnEvent?.('persona_answer', {
        persona_uuid: samplePersona.uuid, question_index: 0, answer: 'authoritative',
      }, 3)
      mockState.capturedOnEvent?.('persona_answer', {
        persona_uuid: samplePersona.uuid, question_index: 0, answer: 'duplicate',
      }, 3)
    })
    expect(useStore.getState().personaStates[samplePersona.uuid].answers[0].answer).toBe('authoritative')
  })

  it('renders question failure inline without failing the persona', () => {
    useStore.setState({ selectedPersonas: [samplePersona], surveyTheme: 'theme', questions: ['質問1'] })
    const { result } = renderHook(() => useSurvey())
    act(() => result.current.startSurvey())
    act(() => mockState.capturedOnEvent?.('persona_error', {
      persona_uuid: samplePersona.uuid, question_index: 0, scope: 'question', message: '安全なエラー',
    }, 2))
    const state = useStore.getState().personaStates[samplePersona.uuid]
    expect(state.status).toBe('waiting')
    expect(state.answers[0]).toMatchObject({ answer: '安全なエラー', failed: true })
  })

  it('requests backend cancellation without closing the observer', () => {
    mockState.cancelSurvey.mockResolvedValue({ run_id: 'run-1', status: 'cancelled' })
    useStore.setState({ selectedPersonas: [samplePersona], surveyTheme: 'theme', questions: ['質問1'] })
    const { result } = renderHook(() => useSurvey())
    act(() => result.current.startSurvey())
    useStore.getState().setCurrentRunId('run-1')
    act(() => result.current.cancelSurvey())
    expect(mockState.cancelSurvey).toHaveBeenCalledWith('run-1')
  })

  it.each([
    ['survey_cancelled', 0],
    ['survey_error', 1],
  ])('ends %s without making the run reportable', (event, failed) => {
    useStore.setState({ selectedPersonas: [samplePersona], surveyTheme: 'theme', questions: ['質問1'] })
    const { result } = renderHook(() => useSurvey())
    act(() => result.current.startSurvey())
    act(() => mockState.capturedOnEvent?.(event, {
      run_id: 'run-1', total: 1, completed: 0, failed, not_completed: 1,
    }, 4))
    expect(useStore.getState().personaStates[samplePersona.uuid].status).toBe('not_completed')
    expect(useStore.getState().surveyLifecycle).toBe(event === 'survey_error' ? 'failed' : 'cancelled')
  })

  it('closes the observer when a terminal event arrives', () => {
    useStore.setState({ selectedPersonas: [samplePersona], surveyTheme: 'theme', questions: ['質問1'] })
    const { result } = renderHook(() => useSurvey())
    act(() => result.current.startSurvey())

    act(() => mockState.capturedOnEvent?.('survey_complete', {
      run_id: 'run-1', total: 1, completed: 1, failed: 0, not_completed: 0,
    }, 4))

    expect(mockState.cancelObserver).toHaveBeenCalledOnce()
  })

  it('ends a partially completed run-level error as failed and closes its observer', () => {
    const secondPersona = { ...samplePersona, uuid: 'persona-2', name: '佐藤花子' }
    useStore.setState({
      selectedPersonas: [samplePersona, secondPersona], surveyTheme: 'theme', questions: ['質問1'],
    })
    const { result } = renderHook(() => useSurvey())
    act(() => result.current.startSurvey())

    act(() => {
      mockState.capturedOnEvent?.('persona_complete', { persona_uuid: samplePersona.uuid, index: 0 }, 3)
      mockState.capturedOnEvent?.('survey_error', {
        run_id: 'run-1', total: 2, completed: 1, failed: 0, not_completed: 1,
      }, 4)
    })

    const state = useStore.getState()
    expect(state.surveyLifecycle).toBe('failed')
    expect(state.personaStates[secondPersona.uuid].status).toBe('not_completed')
    expect(mockState.cancelObserver).toHaveBeenCalledOnce()
  })

  it('closes the observer when a terminal event arrives before startSurveySSE returns its cancel function', () => {
    mockState.emitDuringStart = (onEvent) => onEvent('survey_cancelled', {
      run_id: 'run-1', total: 1, completed: 0, failed: 0, not_completed: 1,
    }, 1)
    useStore.setState({ selectedPersonas: [samplePersona], surveyTheme: 'theme', questions: ['質問1'] })
    const { result } = renderHook(() => useSurvey())

    act(() => result.current.startSurvey())

    expect(mockState.cancelObserver).toHaveBeenCalledOnce()
    expect(useStore.getState().surveyLifecycle).toBe('cancelled')
  })
})
