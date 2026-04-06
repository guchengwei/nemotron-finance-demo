import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PersonaDetailModal from '../components/PersonaDetailModal'
import { useStore } from '../store'
import type { Persona } from '../types'

const MOCK_PERSONA: Persona = {
  uuid: 'p1',
  name: '田中太郎',
  age: 40,
  sex: '男',
  prefecture: '東京都',
  region: '関東',
  occupation: 'エンジニア',
  education_level: '大卒',
  marital_status: '既婚',
  persona: 'テスト人物像',
  professional_persona: '',
  cultural_background: '',
  skills_and_expertise: '',
  hobbies_and_interests: '',
  career_goals_and_ambitions: '',
}

afterEach(() => {
  useStore.getState().resetSurvey()
})

describe('PersonaDetailModal followup button', () => {
  it('renders followup button when onFollowup is provided', () => {
    render(<PersonaDetailModal persona={MOCK_PERSONA} onClose={vi.fn()} onFollowup={vi.fn()} />)
    expect(screen.getByRole('button', { name: /深掘り質問/ })).toBeDefined()
  })

  it('does not render followup button when onFollowup is omitted', () => {
    render(<PersonaDetailModal persona={MOCK_PERSONA} onClose={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /深掘り質問/ })).toBeNull()
  })

  it('calls onFollowup with persona when button is clicked', async () => {
    const user = userEvent.setup()
    const handleFollowup = vi.fn()
    render(<PersonaDetailModal persona={MOCK_PERSONA} onClose={vi.fn()} onFollowup={handleFollowup} />)
    await user.click(screen.getByRole('button', { name: /深掘り質問/ }))
    expect(handleFollowup).toHaveBeenCalledWith(MOCK_PERSONA)
  })
})

describe('PersonaDetailModal followup wiring via Layout store', () => {
  it('sets followupPersona and navigates to step 5 when followup clicked', async () => {
    const user = userEvent.setup()

    // Simulate what Layout.tsx will wire:
    const onFollowup = (persona: Persona) => {
      useStore.getState().setFollowupPersona(persona)
      useStore.getState().closePersonaDetail()
      useStore.getState().setStep(5)
    }

    render(<PersonaDetailModal persona={MOCK_PERSONA} onClose={vi.fn()} onFollowup={onFollowup} />)
    await user.click(screen.getByRole('button', { name: /深掘り質問/ }))

    expect(useStore.getState().followupPersona).toMatchObject({ uuid: 'p1', name: '田中太郎' })
    expect(useStore.getState().activeDetailPersona).toBeNull()
    expect(useStore.getState().currentStep).toBe(5)
  })
})
