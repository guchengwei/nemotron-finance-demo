import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import StepIndicator from '../StepIndicator'
import { useStore } from '../../store'

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

describe('StepIndicator', () => {
  afterEach(() => {
    useStore.getState().resetSurvey()
  })

  it('allows navigating to step 3 when personaStates is non-empty', async () => {
    await act(async () => {
      useStore.setState({
        currentStep: 1,
        selectedPersonas: [],
        personaStates: {
          [samplePersona.uuid]: {
            persona: samplePersona,
            status: 'active',
            answers: [],
            activeAnswer: '',
          },
        },
      })
    })

    render(<StepIndicator />)

    const step3 = screen.getByRole('button', { name: /調査実行/ })
    expect(step3).toBeEnabled()

    await act(async () => {
      fireEvent.click(step3)
    })

    expect(useStore.getState().currentStep).toBe(3)
  })
})
