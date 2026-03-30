import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import QuadrantMatrix from '../components/report-matrix/QuadrantMatrix'
import type { AxisConfig, ScoredPersona } from '../types/matrix-report'

const MOCK_AXES: AxisConfig = {
  x_axis: { name: '関心度', rubric: '', label_low: '関心低い', label_high: '関心高い' },
  y_axis: { name: '利用障壁', rubric: '', label_low: '低障壁', label_high: '高障壁' },
  quadrants: [
    { position: 'top-left', label: '様子見層', subtitle: '低関心・高障壁' },
    { position: 'top-right', label: '潜在採用層', subtitle: '高関心・高障壁' },
    { position: 'bottom-left', label: '慎重観察層', subtitle: '低関心・低障壁' },
    { position: 'bottom-right', label: '即時採用層', subtitle: '高関心・低障壁' },
  ],
}

const MOCK_PERSONA: ScoredPersona = {
  persona_id: 'p1', name: '田中太郎', x_score: 4, y_score: 2,
  keywords: [], quadrant_label: '即時採用層', industry: '小売業', age: 40,
}

describe('QuadrantMatrix', () => {
  it('renders all four quadrant labels', () => {
    render(<QuadrantMatrix axes={MOCK_AXES} personas={[]} />)
    expect(screen.getByText('様子見層')).toBeDefined()
    expect(screen.getByText('潜在採用層')).toBeDefined()
    expect(screen.getByText('慎重観察層')).toBeDefined()
    expect(screen.getByText('即時採用層')).toBeDefined()
  })

  it('renders axis names', () => {
    render(<QuadrantMatrix axes={MOCK_AXES} personas={[]} />)
    expect(screen.getByText('関心度')).toBeDefined()
    expect(screen.getByText('利用障壁')).toBeDefined()
  })

  it('renders persona name as dot label', () => {
    render(<QuadrantMatrix axes={MOCK_AXES} personas={[MOCK_PERSONA]} />)
    expect(screen.getByText('田中太郎')).toBeDefined()
  })

  it('renders no dots when personas array is empty', () => {
    const { container } = render(<QuadrantMatrix axes={MOCK_AXES} personas={[]} />)
    expect(container.querySelectorAll('[class*="text-\\[9px\\]"][class*="font-medium"]')).toHaveLength(0)
  })

  it('renders legend entries for each unique industry', () => {
    const personas: ScoredPersona[] = [
      { ...MOCK_PERSONA, persona_id: 'p1', industry: '小売業' },
      { ...MOCK_PERSONA, persona_id: 'p2', industry: '建設業' },
      { ...MOCK_PERSONA, persona_id: 'p3', industry: '小売業' },
    ]
    render(<QuadrantMatrix axes={MOCK_AXES} personas={personas} />)
    expect(screen.getByText('小売業')).toBeDefined()
    expect(screen.getByText('建設業')).toBeDefined()
  })
})
