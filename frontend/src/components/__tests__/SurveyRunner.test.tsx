import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import SurveyRunner from '../SurveyRunner'
import { useStore } from '../../store'
import { api } from '../../api'

vi.mock('../../api', () => ({
  api: {
    generateReport: vi.fn(),
  },
}))

const cancelSurvey = vi.hoisted(() => vi.fn())
vi.mock('../../hooks/useSurvey', () => ({ useSurvey: () => ({ cancelSurvey }) }))

const personaOne = {
  uuid: 'p1',
  name: '田中太郎',
  age: 35,
  sex: '男',
  prefecture: '東京都',
  region: '関東',
  occupation: '会社員',
  education_level: '大学卒',
  marital_status: '既婚',
  persona: 'テスト用ペルソナ1',
  professional_persona: '会社員',
  cultural_background: '日本',
  skills_and_expertise: '営業',
  hobbies_and_interests: '読書',
  career_goals_and_ambitions: '昇進',
}

const personaTwo = {
  uuid: 'p2',
  name: '佐藤花子',
  age: 41,
  sex: '女',
  prefecture: '大阪府',
  region: '関西',
  occupation: '公務員',
  education_level: '大学卒',
  marital_status: '既婚',
  persona: 'テスト用ペルソナ2',
  professional_persona: '公務員',
  cultural_background: '日本',
  skills_and_expertise: '事務',
  hobbies_and_interests: '散歩',
  career_goals_and_ambitions: '安定',
}

describe('SurveyRunner scoring display', () => {
  it('shows persona averages and progress average using persona-level means', () => {
    Object.defineProperty(HTMLElement.prototype, 'scrollTo', {
      value: vi.fn(),
      writable: true,
    })

    useStore.setState({
      selectedPersonas: [personaOne, personaTwo],
      questions: ['質問1', '質問2'],
      surveyLifecycle: 'active',
      surveyCompleted: 1,
      surveyFailed: 0,
      currentRunId: null,
      currentReport: null,
      currentHistoryRun: null,
      enableThinking: false,
      personaStates: {
        p1: {
          persona: personaOne,
          status: 'complete',
          answers: [
            { question: '質問1', answer: '回答1', score: 4 },
            { question: '質問2', answer: '回答2', score: 5 },
          ],
        },
        p2: {
          persona: personaTwo,
          status: 'active',
          answers: [
            { question: '質問1', answer: '回答1', score: 2 },
          ],
          activeQuestion: 1,
          activeAnswer: '回答中',
        },
      },
    })

    render(<SurveyRunner />)

    expect(screen.getByText('平均スコア:')).toBeInTheDocument()
    expect(screen.getByText('3.3')).toBeInTheDocument()
    expect(screen.getByText('4.5')).toBeInTheDocument()
    expect(screen.getByText('2.0')).toBeInTheDocument()
  })

  it('exposes an explicit cancel control while a run is active', async () => {
    useStore.setState({
      selectedPersonas: [personaOne], currentRunId: 'run-1', surveyLifecycle: 'active',
      surveyCompleted: 0, surveyFailed: 0, currentHistoryRun: null, currentReport: null,
      personaStates: { p1: { persona: personaOne, status: 'active', answers: [] } },
    })
    render(<SurveyRunner />)
    await userEvent.click(screen.getByTestId('cancel-survey-button'))
    expect(cancelSurvey).toHaveBeenCalled()
  })

  it('ends a partially completed cancelled run without offering or generating a report', () => {
    useStore.setState({
      selectedPersonas: [personaOne, personaTwo],
      currentRunId: 'run-1',
      surveyLifecycle: 'cancelled',
      surveyCompleted: 1,
      surveyFailed: 0,
      currentHistoryRun: null,
      currentReport: null,
      personaStates: {
        p1: { persona: personaOne, status: 'complete', answers: [{ question: '質問1', answer: '回答1' }] },
        p2: { persona: personaTwo, status: 'not_completed', answers: [] },
      },
    })

    render(<SurveyRunner />)

    expect(screen.getByText('調査がキャンセルされました')).toBeInTheDocument()
    expect(screen.queryByTestId('cancel-survey-button')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'レポートを見る →' })).not.toBeInTheDocument()
    expect(api.generateReport).not.toHaveBeenCalled()
  })
})
