import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ReportDashboard from '../ReportDashboard'
import { useStore } from '../../store'

vi.mock('../../api', () => ({
  api: {
    generateReport: vi.fn(),
  },
}))

vi.mock('../DemographicCharts', () => ({
  default: () => <div data-testid="demographic-charts" />,
}))

vi.mock('../TopPickCard', () => ({
  default: ({ persona }: { persona?: { age?: number; sex?: string } }) => (
    <div data-testid="mock-top-pick-card">
      {persona ? `${persona.age}/${persona.sex}` : 'missing-persona'}
    </div>
  ),
}))

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
}

describe('ReportDashboard top-pick persona resolution', () => {
  afterEach(() => {
    useStore.getState().resetSurvey()
  })

  it('passes reconstructed history persona data to top-pick cards', async () => {
    await act(async () => {
      useStore.setState({
        currentReport: {
          run_id: 'run-1',
          overall_score: 4.1,
          group_tendency: '前向きです',
          conclusion: '具体的な懸念解消が重要です',
          top_picks: [
            {
              persona_uuid: historyPersona.uuid,
              persona_name: historyPersona.name,
              persona_summary: '佐藤花子、41歳、女性、公務員、大阪府',
              highlight_reason: '前向きな期待があるため',
              highlight_quote: 'まずは試したいです',
            },
          ],
        },
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

    expect(screen.getByTestId('mock-top-pick-card')).toHaveTextContent('41/女')
  })
})
