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
    generateQuestions: vi.fn(),
    getHistory: vi.fn(),
    getHistoryRun: vi.fn(),
    generateReport: vi.fn(),
    deleteHistoryRun: vi.fn(),
    checkReady: vi.fn().mockResolvedValue(true),
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
  financial_literacy: ['初心者', '中級者'],
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
    useStore.setState({ dbReady: true })
    mockedApi.getHistory.mockResolvedValue({ runs: [] })
    mockedApi.getFilters.mockResolvedValue(filtersResponse)
    mockedApi.getSample.mockResolvedValue({ total_matching: 1, sampled: [samplePersona] })
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
})
