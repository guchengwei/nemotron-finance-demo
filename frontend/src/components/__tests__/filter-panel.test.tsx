import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import FilterPanel from '../FilterPanel'
import { api } from '../../api'
import { useStore } from '../../store'

vi.mock('../../api', () => ({
  api: {
    getFilters: vi.fn(),
    getCount: vi.fn(),
    getSample: vi.fn(),
    generateQuestions: vi.fn(),
    getHistory: vi.fn(),
    getHistoryRun: vi.fn(),
    generateReport: vi.fn(),
    deleteHistoryRun: vi.fn(),
  },
}))

const mockedApi = api as typeof api & {
  getCount: ReturnType<typeof vi.fn>
}

const filtersResponse = {
  sex: ['男', '女'],
  age_ranges: ['20-29', '30-39'],
  regions: ['関東', '関西'],
  prefectures: ['東京都', '大阪府'],
  occupations_top50: ['会社員', '公務員'],
  education_levels: ['大学卒', '高校卒'],
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

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('FilterPanel', () => {
  beforeEach(() => {
    useStore.setState({ filters: null })
    mockedApi.getFilters.mockResolvedValue(filtersResponse)
    mockedApi.getCount.mockResolvedValue({ total_matching: 100 })
    mockedApi.getSample.mockResolvedValue({ total_matching: 1, sampled: [sampledPersona] })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('loads filters and displays total count', async () => {
    render(<FilterPanel />)

    expect(await screen.findByText('100')).toBeInTheDocument()
    expect(mockedApi.getFilters).toHaveBeenCalled()
  })

  it('changing filter requests updated hit count', async () => {
    const user = userEvent.setup()
    mockedApi.getCount.mockResolvedValueOnce({ total_matching: 42 })

    render(<FilterPanel />)

    const sexSelect = (await screen.findAllByRole('combobox'))[0]
    await user.selectOptions(sexSelect, '男')

    await waitFor(() => {
      expect(mockedApi.getCount).toHaveBeenCalledWith(expect.objectContaining({ sex: '男' }), expect.any(AbortSignal))
    })
    await screen.findByText('42')
  })

  it('latest filter selection wins over stale response', async () => {
    const user = userEvent.setup()
    const first = deferred<{ total_matching: number }>()
    const second = deferred<{ total_matching: number }>()
    mockedApi.getCount
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)

    render(<FilterPanel />)

    const sexSelect = (await screen.findAllByRole('combobox'))[0]
    await user.selectOptions(sexSelect, '男')
    await new Promise((resolve) => setTimeout(resolve, 300))
    await user.selectOptions(sexSelect, '女')
    await new Promise((resolve) => setTimeout(resolve, 300))

    second.resolve({ total_matching: 7 })
    await waitFor(() => {
      expect(screen.getByTestId('match-count')).toHaveTextContent('7')
    })

    first.resolve({ total_matching: 3 })
    await new Promise((resolve) => setTimeout(resolve, 10))
    expect(screen.getByTestId('match-count')).toHaveTextContent('7')
  })

  it('sampling uses custom count when provided', async () => {
    const user = userEvent.setup()
    render(<FilterPanel />)

    await screen.findByText('100')
    await user.type(screen.getByPlaceholderText('カスタム'), '17')
    await user.click(screen.getByRole('button', { name: 'ペルソナを抽出 (17名)' }))

    await waitFor(() => {
      expect(mockedApi.getSample).toHaveBeenCalledWith(expect.objectContaining({ count: 17 }))
    })
  })

  it('loading state disappears after filters resolve', async () => {
    const pendingFilters = deferred<typeof filtersResponse>()
    mockedApi.getFilters.mockReturnValueOnce(pendingFilters.promise)

    render(<FilterPanel />)

    expect(screen.getByText('データベース読み込み中...')).toBeInTheDocument()

    pendingFilters.resolve(filtersResponse)

    await waitFor(() => {
      expect(screen.queryByText('データベース読み込み中...')).not.toBeInTheDocument()
    })
  })
})
