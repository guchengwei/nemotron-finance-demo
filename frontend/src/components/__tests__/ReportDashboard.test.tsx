import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ReportDashboard from '../ReportDashboard'
import { api } from '../../api'
import { useStore } from '../../store'

vi.mock('../../api', () => ({
  api: {
    generateReport: vi.fn(),
  },
}))

vi.mock('../DemographicCharts', () => ({
  default: () => <div data-testid="demographic-charts" />,
}))

vi.mock('../report-matrix/MatrixReport', () => ({
  default: () => <div data-testid="matrix-report" />,
}))

const selectedPersona = {
  uuid: 'persona-selected',
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

const historyPersona = {
  uuid: 'persona-history',
  name: '佐藤花子',
  age: 41,
  sex: '女',
  prefecture: '大阪府',
  region: '関西',
  occupation: '公務員',
  education_level: '大学卒',
  marital_status: '既婚',
  persona: '履歴から復元されるペルソナ',
  professional_persona: '公務員',
  cultural_background: '日本',
  skills_and_expertise: '事務',
  hobbies_and_interests: '散歩',
  career_goals_and_ambitions: '安定',
  financial_extension: {
    financial_literacy: '中級者',
  },
}

function makeReport(personaUuid: string, personaName: string, personaSummary: string) {
  return {
    run_id: 'run-1',
    overall_score: 4.1,
    group_tendency: '前向きです',
    conclusion_summary: '不安解消を優先すべきです',
    recommended_actions: ['料金を明確にする', '安全性を示す', '試用導線を整える'],
    conclusion: '具体的な懸念解消が重要です',
    demographic_breakdown: {
      by_financial_literacy: {
        初心者: 3.2,
      },
    },
    top_picks: [
      {
        persona_uuid: personaUuid,
        persona_name: personaName,
        persona_summary: personaSummary,
        highlight_reason: '前向きな受容があるため',
        highlight_quote: 'まずは試したいです',
      },
    ],
  }
}

describe('ReportDashboard.handleChatWithPersona', () => {
  afterEach(() => {
    useStore.getState().resetSurvey()
  })

  it('uses a persona from selectedPersonas when available', async () => {
    await act(async () => {
      useStore.setState({
        currentReport: makeReport(selectedPersona.uuid, selectedPersona.name, '田中太郎、35歳、男性、会社員、東京都'),
        selectedPersonas: [selectedPersona],
        currentHistoryRun: null,
      })
    })

    render(<ReportDashboard />)

    await act(async () => {
      fireEvent.click(screen.getByTestId(`top-pick-chat-${selectedPersona.uuid}`))
    })

    expect(useStore.getState().followupPersona).toMatchObject(selectedPersona)
    expect(useStore.getState().currentStep).toBe(5)
  })

  it('reconstructs a persona from currentHistoryRun.answers[].persona_full_json', async () => {
    await act(async () => {
      useStore.setState({
        currentReport: makeReport(historyPersona.uuid, historyPersona.name, '佐藤花子、41歳、女性、公務員、大阪府'),
        selectedPersonas: [],
        currentHistoryRun: {
          id: 'run-1',
          created_at: '2026-03-19T00:00:00',
          survey_theme: 'テスト調査',
          questions: ['質問1'],
          persona_count: 1,
          status: 'completed',
          answers: [
            {
              persona_uuid: historyPersona.uuid,
              persona_summary: '佐藤花子、41歳、女性、公務員、大阪府',
              persona_full_json: JSON.stringify(historyPersona),
              question_index: 0,
              question_text: '質問1',
              answer: '回答',
            },
          ],
          followup_chats: {},
        },
      })
    })

    render(<ReportDashboard />)

    await act(async () => {
      fireEvent.click(screen.getByTestId(`top-pick-chat-${historyPersona.uuid}`))
    })

    expect(useStore.getState().followupPersona).toMatchObject(historyPersona)
    expect(useStore.getState().followupPersona?.financial_extension).toMatchObject({
      financial_literacy: '中級者',
    })
    expect(useStore.getState().currentStep).toBe(5)
  })

  it('renders structured conclusion summary and recommended actions', async () => {
    await act(async () => {
      useStore.setState({
        currentReport: makeReport(selectedPersona.uuid, selectedPersona.name, '田中太郎、35歳、男性、会社員、東京都'),
        selectedPersonas: [selectedPersona],
        currentHistoryRun: null,
      })
    })

    render(<ReportDashboard />)

    expect(screen.getByText('不安解消を優先すべきです')).toBeInTheDocument()
    expect(screen.getByText('料金を明確にする')).toBeInTheDocument()
    expect(screen.getByText('安全性を示す')).toBeInTheDocument()
    expect(screen.getByText('試用導線を整える')).toBeInTheDocument()
  })

  it('falls back to legacy conclusion text when structured fields are absent', async () => {
    await act(async () => {
      useStore.setState({
        currentReport: {
          ...makeReport(selectedPersona.uuid, selectedPersona.name, '田中太郎、35歳、男性、会社員、東京都'),
          conclusion_summary: undefined,
          recommended_actions: [],
          conclusion: '旧形式の結論テキストです',
        },
        selectedPersonas: [selectedPersona],
        currentHistoryRun: null,
      })
    })

    render(<ReportDashboard />)

    expect(screen.getByText('旧形式の結論テキストです')).toBeInTheDocument()
    expect(screen.queryByText('料金を明確にする')).not.toBeInTheDocument()
  })
})

describe('ReportDashboard missing-report recovery', () => {
  afterEach(() => {
    useStore.getState().resetSurvey()
    vi.clearAllMocks()
  })

  it('auto-generates a missing report on mount when a run id exists', async () => {
    vi.mocked(api.generateReport).mockResolvedValue(
      makeReport(selectedPersona.uuid, selectedPersona.name, '田中太郎、35歳、男性、会社員、東京都'),
    )

    await act(async () => {
      useStore.setState({
        currentReport: null,
        currentRunId: 'run-1',
        selectedPersonas: [selectedPersona],
        currentHistoryRun: {
          id: 'run-1',
          created_at: '2026-04-02T00:00:00',
          survey_theme: 'テスト調査',
          questions: ['質問1'],
          persona_count: 1,
          status: 'completed',
          answers: [],
          followup_chats: {},
        },
      })
    })

    render(<ReportDashboard />)

    await waitFor(() => {
      expect(api.generateReport).toHaveBeenCalledWith('run-1')
    })
    expect(await screen.findByRole('button', { name: 'テキストレポート' })).toBeInTheDocument()
    expect(screen.queryByText('レポートがありません')).not.toBeInTheDocument()

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'テキストレポート' }))
    })

    expect(await screen.findByText('前向きです')).toBeInTheDocument()
  })
})
