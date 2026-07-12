import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'
import { api, observeSurvey } from '../../api'
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
    cancelAndDeleteSurvey: vi.fn(),
    checkReady: vi.fn().mockResolvedValue({ ready: true }),
    checkHealth: vi.fn().mockResolvedValue({ status: 'ok', mock_llm: true, llm_reachable: true }),
  },
  observeSurvey: vi.fn(),
}))

vi.mock('../../hooks/useSurvey', () => ({
  useSurvey: () => ({
    startSurvey: vi.fn(),
    cancelSurvey: vi.fn(),
  }),
}))

const mockedApi = api as unknown as Record<string, ReturnType<typeof vi.fn>>
const mockedObserveSurvey = vi.mocked(observeSurvey)

const filtersResponse = {
  sex: ['男', '女'],
  age_ranges: ['20-29', '30-39'],
  regions: ['関東'],
  prefectures: ['東京都'],
  occupations_top50: ['会社員'],
  education_levels: ['大学卒'],
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

afterEach(() => {
  vi.useRealTimers()
})

describe('Sidebar new survey', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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

  it('new survey remounts step one with default filters and no count request', async () => {
    vi.useFakeTimers()
    useStore.setState({ selectedPersonas: [sampledPersona] })

    try {
      render(<App />)

      expect(screen.getByText('設定済み（閲覧のみ）')).toBeInTheDocument()
      expect(screen.getByText('1名 抽出済み')).toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: '＋ 新規調査' }))

      await act(async () => {
        await Promise.resolve()
      })
      expect(screen.getByRole('heading', { name: 'ペルソナ選択' })).toBeInTheDocument()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(300)
      })

      const [sexSelect, regionSelect, prefectureSelect, educationSelect] = screen.getAllByRole('combobox')
      const [ageMinInput, ageMaxInput] = screen.getAllByRole('spinbutton')
      const occupationInput = screen.getByPlaceholderText('職業を入力...')

      expect(sexSelect).toHaveValue('')
      expect(regionSelect).toHaveValue('')
      expect(prefectureSelect).toHaveValue('')
      expect(occupationInput).toHaveValue('')
      expect(educationSelect).toHaveValue('')
      expect(ageMinInput).toHaveValue(20)
      expect(ageMaxInput).toHaveValue(80)
      expect(mockedApi.getCount).toHaveBeenCalledTimes(0)
    } finally {
      vi.useRealTimers()
    }
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

  it('cancels a running survey before deleting it', async () => {
    const user = userEvent.setup()
    mockedApi.getHistory.mockResolvedValue({ runs: [{
      id: 'run-active', created_at: '2026-03-18T00:00:00',
      survey_theme: '実行中テーマ', persona_count: 2, status: 'running',
    }] })
    mockedApi.cancelAndDeleteSurvey.mockResolvedValue(undefined)

    render(<App />)
    expect(await screen.findByText('実行中テーマ')).toBeInTheDocument()
    await user.click(screen.getByTestId('delete-run-run-active'))

    await waitFor(() => expect(mockedApi.cancelAndDeleteSurvey).toHaveBeenCalledWith('run-active'))
    expect(mockedApi.deleteHistoryRun).not.toHaveBeenCalledWith('run-active')
    expect(screen.queryByText('実行中テーマ')).not.toBeInTheDocument()
  })
})

describe('Sidebar running-run reattachment', () => {
  it('hydrates persona snapshots and attaches an observer', async () => {
    const user = userEvent.setup()
    const run = { id: 'running-1', created_at: '2026-03-18T00:00:00', survey_theme: '再接続', persona_count: 1, status: 'running' }
    mockedApi.getHistory.mockResolvedValue({ runs: [run] })
    mockedApi.getHistoryRun.mockResolvedValue({
      ...run, questions: ['質問'], answers: [], followup_chats: {}, replay_available: true,
      personas: [{ persona_uuid: sampledPersona.uuid, position: 0, persona_summary: '田中太郎', persona_full_json: JSON.stringify(sampledPersona), persona: sampledPersona }],
    })
    mockedObserveSurvey.mockReturnValue(vi.fn())
    render(<App />)
    await user.click(await screen.findByText('再接続'))
    await waitFor(() => expect(mockedObserveSurvey).toHaveBeenCalledWith(
      'running-1', expect.any(Function), expect.any(Function), expect.any(Function),
    ))
    expect(useStore.getState().selectedPersonas[0].uuid).toBe(sampledPersona.uuid)
    expect(screen.getByTestId('survey-runner-screen')).toBeVisible()
  })
})

describe('Sidebar failed-run restoration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useStore.getState().resetSurvey()
    useStore.setState({ dbReady: true })
    mockedApi.getFilters.mockResolvedValue(filtersResponse)
    mockedApi.getCount.mockResolvedValue({ total_matching: 100 })
    mockedApi.checkReady.mockResolvedValue({ ready: true })
    mockedApi.checkHealth.mockResolvedValue({ status: 'ok', mock_llm: true, llm_reachable: true })
  })

  it('renders a restored failed run as non-reportable error even when failed count is zero', async () => {
    Object.defineProperty(HTMLElement.prototype, 'scrollTo', {
      value: vi.fn(),
      writable: true,
    })
    const user = userEvent.setup()
    const run = {
      id: 'failed-1', created_at: '2026-03-18T00:00:00', survey_theme: '障害終了',
      persona_count: 1, status: 'failed',
    }
    mockedApi.getHistory.mockResolvedValue({ runs: [run] })
    mockedApi.getHistoryRun.mockResolvedValue({
      ...run,
      questions: ['質問'],
      answers: [{
        persona_uuid: sampledPersona.uuid,
        persona_summary: sampledPersona.name,
        persona_full_json: JSON.stringify(sampledPersona),
        question_index: 0,
        question_text: '質問',
        answer: '途中回答',
        outcome: 'answered',
      }],
      followup_chats: {},
      personas: [{
        persona_uuid: sampledPersona.uuid,
        position: 0,
        persona_summary: sampledPersona.name,
        persona_full_json: JSON.stringify(sampledPersona),
        persona: sampledPersona,
      }],
    })

    render(<App />)
    await user.click(await screen.findByText('障害終了'))

    expect(await screen.findByRole('heading', { name: '調査エラー' })).toBeInTheDocument()
    expect(useStore.getState().surveyLifecycle).toBe('failed')
    expect(useStore.getState().surveyFailed).toBe(0)
    expect(screen.queryByRole('button', { name: 'レポートを見る →' })).not.toBeInTheDocument()
    expect(mockedApi.generateReport).not.toHaveBeenCalled()
  })
})
