import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import SurveyRunner from '../SurveyRunner'
import { useStore } from '../../store'

vi.mock('../../api', () => ({
  api: {
    generateReport: vi.fn(),
  },
}))

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
      surveyComplete: false,
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
})
