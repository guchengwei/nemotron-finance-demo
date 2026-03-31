import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent, screen } from '@testing-library/react'
import MatrixReport from '../components/report-matrix/MatrixReport'
import type { Persona } from '../types'

// Mock components to avoid complex dependencies
vi.mock('../components/report-matrix/QuadrantMatrix', () => ({
  default: ({ onPersonaClick }: any) => (
    <button data-testid="persona-dot" onClick={() => onPersonaClick({ persona_id: 'p1', keywords: [] })}>
      Click Persona
    </button>
  ),
}))

vi.mock('../components/report-matrix/KeywordPanel', () => ({
  default: () => <div>Keywords</div>,
}))

vi.mock('../components/report-matrix/RecommendationCards', () => ({
  default: () => <div>Recommendations</div>,
}))

vi.mock('../components/report-matrix/ScoreTable', () => ({
  default: ({ onRowClick }: any) => (
    <button data-testid="score-row" onClick={() => onRowClick({ persona_id: 'p1', keywords: [] })}>
      Click Row
    </button>
  ),
}))

// Mock Zustand store
vi.mock('../store', () => ({
  useStore: vi.fn((selector: (s: unknown) => unknown) => {
    const state = {
      matrixReport: {
        status: 'complete',
        axes: {
          x_axis: { name: 'test', rubric: '', label_low: '', label_high: '' },
          y_axis: { name: 'test', rubric: '', label_low: '', label_high: '' },
          quadrants: [],
        },
        personas: [{ persona_id: 'p1', x_score: 3, y_score: 3, keywords: [] }],
        keywords: null,
        recommendations: [],
        scoreTable: [],
        errorMessage: '',
      },
      setMatrixReport: vi.fn(),
      selectedPersonas: [] as Persona[],
      currentHistoryRun: {
        answers: [
          { persona_uuid: 'p1', persona_full_json: '{ not valid json !!!' },
        ],
      },
      openPersonaDetail: vi.fn(),
    }
    return selector(state)
  }),
}))

vi.mock('../api', () => ({
  startMatrixReportSSE: vi.fn(() => () => {}),
}))

describe('MatrixReport', () => {
  it('does not throw when persona_full_json is invalid JSON', () => {
    expect(() => {
      render(<MatrixReport surveyId="test-run-1" />)
    }).not.toThrow()
  })

  it('does not throw when clicking a persona dot with invalid persona_full_json', () => {
    expect(() => {
      render(<MatrixReport surveyId="test-run-1" />)
      const dot = screen.getByTestId('persona-dot')
      fireEvent.click(dot)
    }).not.toThrow()
  })
})
