import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import FollowUpChat from '../FollowUpChat'
import { api, startFollowupSSE } from '../../api'
import { useStore } from '../../store'

vi.mock('../../api', () => ({
  api: {
    getFollowupSuggestions: vi.fn(),
    clearFollowupHistory: vi.fn(),
  },
  startFollowupSSE: vi.fn(),
}))

vi.mock('../PersonaAvatar', () => ({
  default: ({ name }: { name: string }) => <div data-testid="persona-avatar">{name}</div>,
}))

const mockedStartFollowupSSE = vi.mocked(startFollowupSSE)
const mockedApi = vi.mocked(api)

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
    mockedApi.getFollowupSuggestions?.mockResolvedValue({ questions: ['履歴質問1', '履歴質問2', '履歴質問3'] } as never)
  })

  it('clears suggestion chips immediately when the user sends a message', async () => {
    const user = userEvent.setup()
    mockedStartFollowupSSE.mockReturnValue(vi.fn())

    render(<FollowUpChat />)

    expect(await screen.findByRole('button', { name: '履歴質問1' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /具体的にどの程度の手数料/ })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '履歴質問1' }))

    // Suggestions must be cleared immediately on send (before response arrives)
    expect(screen.queryByRole('button', { name: '履歴質問1' })).not.toBeInTheDocument()
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
    await screen.findByRole('button', { name: '履歴質問1' })

    expect(screen.getByText('前回の回答')).toBeInTheDocument()

    await user.type(screen.getByTestId('followup-input'), '未送信の入力')
    await user.click(screen.getByRole('button', { name: '送信' }))

    await act(async () => {
      useStore.setState({ followupPersona: personaB })
      await Promise.resolve()
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

  it('refreshes suggestions after a completed answer', async () => {
    const user = userEvent.setup()
    let onDone: ((text: string) => void) | undefined

    mockedApi.getFollowupSuggestions
      .mockResolvedValueOnce({ questions: ['初期候補1', '初期候補2', '初期候補3'] } as never)
      .mockResolvedValueOnce({ questions: ['更新候補1', '更新候補2', '更新候補3'] } as never)

    mockedStartFollowupSSE.mockImplementation((_request, _onToken, handleDone) => {
      onDone = handleDone
      return vi.fn()
    })

    render(<FollowUpChat />)

    expect(await screen.findByRole('button', { name: '初期候補1' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '初期候補1' }))

    await act(async () => {
      onDone?.('回答完了')
    })

    expect(await screen.findByRole('button', { name: '更新候補1' })).toBeInTheDocument()
  })

  it('keeps the suggestion rail wrapped after conversation starts', async () => {
    const user = userEvent.setup()
    mockedStartFollowupSSE.mockReturnValue(vi.fn())

    render(<FollowUpChat />)

    const initialChip = await screen.findByRole('button', { name: '履歴質問1' })
    const rail = initialChip.parentElement as HTMLElement

    expect(rail.className).toContain('flex-wrap')
    expect(rail.className).not.toContain('whitespace-nowrap')

    await user.click(initialChip)

    expect(rail.className).toContain('flex-wrap')
    expect(rail.className).not.toContain('whitespace-nowrap')
    expect(rail.className).not.toContain('overflow-x-auto')
  })

  it('keeps completed follow-up turns in store-backed history when switching personas', async () => {
    const user = userEvent.setup()
    let onDone: ((text: string) => void) | undefined

    mockedStartFollowupSSE.mockImplementation((_request, _onToken, handleDone) => {
      onDone = handleDone
      return vi.fn()
    })

    render(<FollowUpChat />)
    await screen.findByRole('button', { name: '履歴質問1' })

    await user.type(screen.getByTestId('followup-input'), '保存される質問')
    await user.click(screen.getByRole('button', { name: '送信' }))

    await act(async () => {
      onDone?.('保存される回答')
    })

    await act(async () => {
      useStore.setState({ followupPersona: personaB })
      await Promise.resolve()
    })
    await act(async () => {
      useStore.setState({ followupPersona: personaA })
      await Promise.resolve()
    })

    expect(screen.getByText('保存される回答')).toBeInTheDocument()
  })

  it('does not show suggestion chips that look like JSON objects or dicts', async () => {
    mockedApi.getFollowupSuggestions?.mockResolvedValue({
      questions: [
        "{'question': '質問A', 'reason': '理由'}",
        '{"q": "質問B"}',
        '有効な日本語の質問？',
      ],
    } as never)

    render(<FollowUpChat />)

    await screen.findByRole('button', { name: '有効な日本語の質問？' })

    expect(screen.queryAllByRole('button', { name: /[{}]/ })).toHaveLength(0)
  })

  it('clears follow-up history for the selected persona after confirmation', async () => {
    const user = userEvent.setup()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    mockedApi.clearFollowupHistory?.mockResolvedValue({ deleted_count: 1 } as never)

    render(<FollowUpChat />)

    expect(await screen.findByRole('button', { name: '履歴質問1' })).toBeInTheDocument()
    expect(screen.getByText('前回の回答')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '履歴を消去' }))

    expect(confirmSpy).toHaveBeenCalled()
    expect(mockedApi.clearFollowupHistory).toHaveBeenCalledWith('run-1', 'persona-a')
    expect(screen.queryByText('前回の回答')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '履歴質問1' })).toBeInTheDocument()
    expect(useStore.getState().currentHistoryRun?.followup_chats['persona-a']).toEqual([])

    confirmSpy.mockRestore()
  })
})
