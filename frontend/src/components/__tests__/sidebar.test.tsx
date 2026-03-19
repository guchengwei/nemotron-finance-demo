import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'
import { api } from '../../api'
import { useStore } from '../../store'

vi.mock('../../api', () => ({
  api: {
    getFilters: vi.fn(),
    getCount: vi.fn(),
    getSample: vi.fn(),
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

const mockedApi = api as unknown as Record<string, ReturnType<typeof vi.fn>>

const filtersResponse = {
  sex: ['男', '女'],
  age_ranges: ['20-29', '30-39'],
  regions: ['関東'],
  prefectures: ['東京都'],
  occupations_top50: ['会社員'],
  education_levels: ['大学卒'],
  financial_literacy: ['初心者', '中級者'],
  total_count: 100,
}

const sampledPersona = {
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

describe('Sidebar new survey', () => {
  beforeEach(() => {
    useStore.setState({ dbReady: true })
    mockedApi.getHistory.mockResolvedValue({ runs: [] })
    mockedApi.getFilters.mockResolvedValue(filtersResponse)
    mockedApi.getCount.mockResolvedValue({ total_matching: 100 })
    mockedApi.getSample.mockResolvedValue({ total_matching: 1, sampled: [sampledPersona] })
  })

  it('new survey resets visible step-one state', async () => {
    const user = userEvent.setup()
    render(<App />)

    const sexSelect = (await screen.findAllByRole('combobox'))[0]
    await user.selectOptions(sexSelect, '男')
    await user.click(screen.getByRole('button', { name: 'ペルソナを抽出 (8名)' }))

    expect(await screen.findByText('田中太郎')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '＋ 新規調査' }))

    await waitFor(() => {
      expect(screen.queryByText('田中太郎')).not.toBeInTheDocument()
    })
    expect(screen.getByRole('heading', { name: 'ペルソナ選択' })).toBeInTheDocument()
  })

  it('new survey returns from later step to step one', async () => {
    const user = userEvent.setup()
    useStore.setState({
      dbReady: true,
      currentStep: 4,
      currentReport: {
        run_id: 'run-1',
        overall_score: 4.2,
        top_picks: [],
      },
      surveyTheme: '既存テーマ',
      filters: filtersResponse,
    })

    render(<App />)

    await user.click(screen.getByRole('button', { name: '＋ 新規調査' }))

    expect(await screen.findByRole('heading', { name: 'ペルソナ選択' })).toBeInTheDocument()
  })
})

describe('Sidebar delete', () => {
  beforeEach(() => {
    useStore.setState({ dbReady: true })
    mockedApi.getFilters.mockResolvedValue(filtersResponse)
    mockedApi.getCount.mockResolvedValue({ total_matching: 100 })
  })

  it('delete button removes history entry', async () => {
    const user = userEvent.setup()
    const mockRun = {
      id: 'run-1',
      created_at: '2026-03-18T00:00:00',
      survey_theme: 'テストテーマ',
      persona_count: 8,
      status: 'completed',
      overall_score: 3.5,
    }
    mockedApi.getHistory.mockResolvedValue({ runs: [mockRun] })
    mockedApi.deleteHistoryRun.mockResolvedValue(undefined)

    render(<App />)

    expect(await screen.findByText('テストテーマ')).toBeInTheDocument()

    const deleteBtn = screen.getByTestId('delete-run-run-1')
    await user.click(deleteBtn)

    await waitFor(() => {
      expect(screen.queryByText('テストテーマ')).not.toBeInTheDocument()
    })
    expect(mockedApi.deleteHistoryRun).toHaveBeenCalledWith('run-1')
  })
})
