import { describe, expect, it } from 'vitest'

import { useStore } from '../store'
import { DEFAULT_SURVEY_QUESTIONS, SURVEY_PRESETS } from './surveyPresets'

describe('surveyPresets config module', () => {
  it('exports the shared presets and default questions used by the store reset flow', () => {
    useStore.setState({
      surveyTheme: 'changed',
      questions: ['changed'],
      surveyLabel: 'changed',
    })

    useStore.getState().resetSurvey()

    expect(SURVEY_PRESETS.length).toBeGreaterThan(0)
    expect(DEFAULT_SURVEY_QUESTIONS.length).toBeGreaterThan(0)
    expect(useStore.getState().questions).toEqual(DEFAULT_SURVEY_QUESTIONS)
  })
})
