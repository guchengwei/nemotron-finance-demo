import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import FollowUpChat from '../FollowUpChat'
import { startFollowupSSE } from '../../api'
import { useStore } from '../../store'

vi.mock('../../api', () => ({
  startFollowupSSE: vi.fn(),
}))

vi.mock('../PersonaAvatar', () => ({
  default: ({ name }: { name: string }) => <div data-testid="persona-avatar">{name}</div>,
}))

const mockedStartFollowupSSE = vi.mocked(startFollowupSSE)

const personaA = {
  uuid: 'persona-a',
  name: '田中太郎',
  age: 35,
  sex: '男',
  prefecture: '東京都',
  region: '関東',
  occupation: '会社員',
  education_level: '大学卒',
  marital_status: '既婚',
  persona: 'テスト用ペルソナA',
  professional_persona: '会社員',
  cultural_background: '日本',
  skills_and_expertise: '営業',
  hobbies_and_interests: '読書',
  career_goals_and_ambitions: '昇進',
}

const personaB = {
  ...personaA,
  uuid: 'persona-b',
  name: '佐藤花子',
  sex: '女',
  persona: 'テスト用ペルソナB',
}

function seedStore() {
  useStore.setState({
    followupPersona: personaA,
    currentRunId: 'run-1',
    surveyTheme: 'AI投資アドバイザー',
    questions: [
      '料金体系についてどのようにお考えですか？',
      'AIによる提案をどの程度信頼できますか？（1:低い〜5:高い）',
      '料金体系についてどのようにお考えですか？',
    ],
    currentHistoryRun: {
      id: 'run-1',
      created_at: '2026-03-20T00:00:00',
      survey_theme: 'AI投資アドバイザー',
      questions: ['履歴質問1', '履歴質問2'],
      persona_count: 2,
      status: 'completed',
      answers: [],
      followup_chats: {
        'persona-a': [{ role: 'assistant', content: '前回の回答' }],
        'persona-b': [],
      },
    },
  })
}

function setScrollMetrics(element: HTMLElement, { scrollTop }: { scrollTop: number }) {
  Object.defineProperty(element, 'scrollHeight', { value: 800, configurable: true })
  Object.defineProperty(element, 'clientHeight', { value: 200, configurable: true })
  Object.defineProperty(element, 'scrollTop', { value: scrollTop, writable: true, configurable: true })
}

describe('FollowUpChat', () => {
  beforeEach(() => {
    seedStore()
  })

  it('keeps survey-derived suggestions visible after conversation starts', async () => {
    const user = userEvent.setup()
    mockedStartFollowupSSE.mockReturnValue(vi.fn())

    render(<FollowUpChat />)

    expect(screen.getByRole('button', { name: '履歴質問1' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /具体的にどの程度の手数料/ })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '履歴質問1' }))

    expect(screen.getByRole('button', { name: '履歴質問1' })).toBeInTheDocument()
  })

  it('stops auto-follow when the user scrolls away from the bottom', async () => {
    const user = userEvent.setup()
    const cancel = vi.fn()
    let onToken: ((text: string) => void) | undefined

    mockedStartFollowupSSE.mockImplementation((_request, handleToken) => {
      onToken = handleToken
      return cancel
    })

    render(<FollowUpChat />)

    const messages = screen.getByTestId('followup-messages')
    const scrollTo = vi.fn()
    Object.defineProperty(messages, 'scrollTo', { value: scrollTo, configurable: true })
    setScrollMetrics(messages, { scrollTop: 600 })

    await user.type(screen.getByTestId('followup-input'), '新しい質問')
    await user.click(screen.getByRole('button', { name: '送信' }))

    const scrollCallsAfterSend = scrollTo.mock.calls.length
    setScrollMetrics(messages, { scrollTop: 0 })
    fireEvent.scroll(messages)

    await act(async () => {
      onToken?.('途中経過')
    })

    expect(scrollTo).toHaveBeenCalledTimes(scrollCallsAfterSend)
  })

  it('cancels active streams and clears stale messages when persona changes', async () => {
    const user = userEvent.setup()
    const cancel = vi.fn()

    mockedStartFollowupSSE.mockReturnValue(cancel)

    render(<FollowUpChat />)

    expect(screen.getByText('前回の回答')).toBeInTheDocument()

    await user.type(screen.getByTestId('followup-input'), '未送信の入力')
    await user.click(screen.getByRole('button', { name: '送信' }))

    act(() => {
      useStore.setState({ followupPersona: personaB })
    })

    expect(cancel).toHaveBeenCalled()
    expect(screen.queryByText('前回の回答')).not.toBeInTheDocument()
    expect(screen.getByTestId('followup-input')).toHaveValue('')
  })

  it('replaces the streaming placeholder with a stable error message on SSE failure', async () => {
    const user = userEvent.setup()
    let onError: ((error: Error) => void) | undefined
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    mockedStartFollowupSSE.mockImplementation((_request, _handleToken, _handleDone, handleError) => {
      onError = handleError
      return vi.fn()
    })

    render(<FollowUpChat />)

    await user.type(screen.getByTestId('followup-input'), '失敗する質問')
    await user.click(screen.getByRole('button', { name: '送信' }))

    await act(async () => {
      onError?.(new Error('network failed'))
    })

    expect(screen.getByText('回答の取得に失敗しました。もう一度お試しください。')).toBeInTheDocument()
    expect(screen.queryByText('思考中')).not.toBeInTheDocument()
    consoleError.mockRestore()
  })
})
