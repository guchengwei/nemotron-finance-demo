import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'
import { api } from '../../api'
import { useStore } from '../../store'

vi.mock('../../api', () => ({
  api: {
    getFilters: vi.fn(),
    getSample: vi.fn(),
    getCount: vi.fn(),
    generateQuestions: vi.fn(),
    getHistory: vi.fn(),
    getHistoryRun: vi.fn(),
    generateReport: vi.fn(),
    deleteHistoryRun: vi.fn(),
    checkReady: vi.fn().mockResolvedValue({ ready: true }),
    checkHealth: vi.fn().mockResolvedValue({ status: 'ok', mock_llm: true, llm_reachable: true }),
  },
}))

vi.mock('../../hooks/useSurvey', () => ({
  useSurvey: () => ({
    startSurvey: vi.fn(),
    cancelSurvey: vi.fn(),
  }),
}))

const mockedApi = vi.mocked(api)

const filtersResponse = {
  sex: ['男', '女'],
  age_ranges: ['20-29', '30-39'],
  regions: ['関東'],
  prefectures: ['東京都'],
  occupations_top50: ['会社員'],
  education_levels: ['大学卒'],
  total_count: 120,
}

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

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('App navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useStore.setState({
      currentStep: 1,
      filters: null,
      selectedPersonas: [],
      surveyTheme: '',
      questions: [],
      surveyLabel: '',
      currentRunId: null,
      personaStates: {},
      surveyComplete: false,
      surveyCompleted: 0,
      surveyFailed: 0,
      currentReport: null,
      followupPersona: null,
      history: [],
      currentHistoryRun: null,
      dbReady: true,
      llmStatus: null,
      enableThinking: false,
      activeDetailPersona: null,
      resetVersion: 0,
    })
    mockedApi.getHistory.mockResolvedValue({ runs: [] })
    mockedApi.getFilters.mockResolvedValue(filtersResponse)
    mockedApi.getCount.mockResolvedValue({ total_matching: 120 })
    mockedApi.getSample.mockResolvedValue({ total_matching: 1, sampled: [samplePersona] })
    mockedApi.checkReady.mockResolvedValue({ ready: true })
    mockedApi.checkHealth.mockResolvedValue({ status: 'ok', mock_llm: true, llm_reachable: true })
  })

  it('transitions from loading to welcome screen when readiness completes without a hook-order crash', async () => {
    useStore.setState({
      dbReady: false,
      currentStep: 1,
      selectedPersonas: [],
      currentHistoryRun: null,
      currentRunId: null,
      personaStates: {},
    })
    mockedApi.checkReady.mockResolvedValueOnce({ ready: true })

    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    try {
      render(<App />)

      expect(screen.getByText('データベースを準備中...')).toBeInTheDocument()
      expect(await screen.findByText('Nemotron Financial Survey Demo')).toBeInTheDocument()
      expect(
        consoleError.mock.calls.some((call) =>
          call.some((arg) => String(arg).includes('Rendered more hooks than during the previous render')),
        ),
      ).toBe(false)
    } finally {
      consoleError.mockRestore()
    }
  })

  it('clicking custom survey opens config screen', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: 'カスタム調査を始める' }))

    expect(await screen.findByRole('heading', { name: '調査設定' })).toBeInTheDocument()
  })

  it('clicking quick demo shows immediate pending state', async () => {
    const user = userEvent.setup()
    const pendingSample = deferred<{ total_matching: number; sampled: typeof samplePersona[] }>()
    mockedApi.getSample.mockReturnValueOnce(pendingSample.promise)

    render(<App />)

    const button = screen.getByRole('button', { name: /デモを実行/ })
    await user.click(button)

    await waitFor(() => {
      expect(button).toBeDisabled()
    })
  })

  it('quick demo transitions to survey runner after sample resolves', async () => {
    const user = userEvent.setup()
    const pendingSample = deferred<{ total_matching: number; sampled: typeof samplePersona[] }>()
    mockedApi.getSample.mockReturnValueOnce(pendingSample.promise)

    render(<App />)

    await user.click(screen.getByRole('button', { name: /デモを実行/ }))
    pendingSample.resolve({ total_matching: 1, sampled: [samplePersona] })

    expect(await screen.findByRole('heading', { name: '調査実行中...' })).toBeInTheDocument()
  })

  it('transitions from loading state to the home screen when readiness succeeds', async () => {
    useStore.setState({ dbReady: false })
    mockedApi.checkReady.mockResolvedValueOnce({ ready: true })
    mockedApi.checkHealth.mockResolvedValueOnce({ status: 'ok', mock_llm: false, llm_reachable: true })

    render(<App />)

    expect(screen.getByText('データベースを準備中...')).toBeInTheDocument()
    expect(await screen.findByTestId('quick-demo-button')).toBeInTheDocument()
  })

  it('keeps rendering the app when health check fails after readiness succeeds', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    useStore.setState({ dbReady: false })
    mockedApi.checkReady.mockResolvedValueOnce({ ready: true })
    mockedApi.checkHealth.mockRejectedValueOnce(new Error('invalid health payload'))

    render(<App />)

    expect(await screen.findByTestId('quick-demo-button')).toBeInTheDocument()
    await waitFor(() => {
      expect(useStore.getState().llmStatus).toEqual({ mock_llm: false, llm_reachable: false })
    })

    consoleError.mockRestore()
  })
})
