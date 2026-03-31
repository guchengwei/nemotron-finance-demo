import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import KeywordPanel from '../components/report-matrix/KeywordPanel'
import RecommendationCards from '../components/report-matrix/RecommendationCards'
import ScoreTable from '../components/report-matrix/ScoreTable'
import type { KeywordSummary, Recommendation, ScoreTableRow, AxisConfig } from '../types/matrix-report'

const MOCK_KEYWORDS: KeywordSummary = {
  strengths: [
    { text: '手数料の安さ', polarity: 'strength', count: 3, elaboration: '', persona_names: ['A', 'B', 'C'] },
    { text: '24時間利用', polarity: 'strength', count: 2, elaboration: '', persona_names: ['A', 'B'] },
  ],
  weaknesses: [
    { text: 'セキュリティ不安', polarity: 'weakness', count: 4, elaboration: '', persona_names: ['A', 'B', 'C', 'D'] },
  ],
}

const MOCK_RECS: Recommendation[] = [
  { title: '段階的な移行支援', highlight_tag: '併用モデル', body: '地方銀行との併用で不安を緩和' },
  { title: '地域特化コンテンツ', highlight_tag: '地産地消', body: '高知の地産地消に特化した機能' },
]

const MOCK_ROWS: ScoreTableRow[] = [
  { persona_id: 'p1', name: '田中', x_score: 4, y_score: 2, industry: '小売業', age: 40, quadrant_label: '即時採用層' },
  { persona_id: 'p2', name: '佐藤', x_score: 2, y_score: 4, industry: '建設業', age: 35, quadrant_label: '様子見層' },
]

const MOCK_AXES: AxisConfig = {
  x_axis: { name: '関心度', rubric: '', label_low: '', label_high: '' },
  y_axis: { name: '利用障壁', rubric: '', label_low: '', label_high: '' },
  quadrants: [],
}

describe('KeywordPanel', () => {
  it('renders strength keywords', () => {
    render(<KeywordPanel keywords={MOCK_KEYWORDS} />)
    expect(screen.getByText('手数料の安さ')).toBeDefined()
    expect(screen.getByText('24時間利用')).toBeDefined()
  })

  it('renders weakness keywords', () => {
    render(<KeywordPanel keywords={MOCK_KEYWORDS} />)
    expect(screen.getByText('セキュリティ不安')).toBeDefined()
  })

  it('shows count as ×N format', () => {
    render(<KeywordPanel keywords={MOCK_KEYWORDS} />)
    const strengthCount = MOCK_KEYWORDS.strengths[0].count
    const weaknessCount = MOCK_KEYWORDS.weaknesses[0].count
    expect(screen.getByText(`×${strengthCount}`)).toBeDefined()
    expect(screen.getByText(`×${weaknessCount}`)).toBeDefined()
  })

  it('renders two separate panel cards', () => {
    const { container } = render(<KeywordPanel keywords={MOCK_KEYWORDS} />)
    const cards = container.querySelectorAll('.shadow-card')
    expect(cards.length).toBe(2)
  })

  it('renders elaboration text when present', () => {
    const withElab = {
      ...MOCK_KEYWORDS,
      strengths: [
        { ...MOCK_KEYWORDS.strengths[0], elaboration: '複数名が低コストを評価' },
      ],
    }
    render(<KeywordPanel keywords={withElab} />)
    expect(screen.getByText('複数名が低コストを評価')).toBeDefined()
  })
})

describe('RecommendationCards', () => {
  it('renders all recommendation titles', () => {
    render(<RecommendationCards recommendations={MOCK_RECS} />)
    expect(screen.getByText(/段階的な移行支援/)).toBeDefined()
    expect(screen.getByText(/地域特化コンテンツ/)).toBeDefined()
  })

  it('renders highlight tags', () => {
    render(<RecommendationCards recommendations={MOCK_RECS} />)
    expect(screen.getByText('併用モデル')).toBeDefined()
    expect(screen.getByText('地産地消')).toBeDefined()
  })

  it('renders empty state when no recommendations', () => {
    render(<RecommendationCards recommendations={[]} />)
    expect(screen.getByText('提案を生成中...')).toBeDefined()
  })

  it('renders recommendations in grid layout', () => {
    const { container } = render(<RecommendationCards recommendations={MOCK_RECS} />)
    const grid = container.querySelector('.grid')
    expect(grid).not.toBeNull()
  })

  it('renders numbered titles with ① ② prefix', () => {
    render(<RecommendationCards recommendations={MOCK_RECS} />)
    expect(screen.getByText(/①/)).toBeDefined()
    expect(screen.getByText(/②/)).toBeDefined()
  })
})

describe('ScoreTable', () => {
  it('renders all persona names', () => {
    render(<ScoreTable rows={MOCK_ROWS} axes={MOCK_AXES} />)
    expect(screen.getByText('田中')).toBeDefined()
    expect(screen.getByText('佐藤')).toBeDefined()
  })

  it('renders quadrant labels', () => {
    render(<ScoreTable rows={MOCK_ROWS} axes={MOCK_AXES} />)
    expect(screen.getByText('即時採用層')).toBeDefined()
    expect(screen.getByText('様子見層')).toBeDefined()
  })

  it('renders axis column headers', () => {
    render(<ScoreTable rows={MOCK_ROWS} axes={MOCK_AXES} />)
    expect(screen.getByText('関心度')).toBeDefined()
    expect(screen.getByText('利用障壁')).toBeDefined()
  })

  it('renders 氏名 column header', () => {
    render(<ScoreTable rows={MOCK_ROWS} axes={MOCK_AXES} />)
    expect(screen.getByText('氏名')).toBeDefined()
  })

  it('renders 業種・年齢 combined column', () => {
    render(<ScoreTable rows={MOCK_ROWS} axes={MOCK_AXES} />)
    const firstRow = MOCK_ROWS[0]
    expect(screen.getByText(`${firstRow.industry}・${firstRow.age}歳`)).toBeDefined()
  })

  it('renders 分類 column header', () => {
    render(<ScoreTable rows={MOCK_ROWS} axes={MOCK_AXES} />)
    expect(screen.getByText('分類')).toBeDefined()
  })

  it('renders star badge for 即時採用層', () => {
    render(<ScoreTable rows={MOCK_ROWS} axes={MOCK_AXES} />)
    expect(screen.getByText('★')).toBeDefined()
  })

  it('renders barrier level as text chip not number', () => {
    render(<ScoreTable rows={MOCK_ROWS} axes={MOCK_AXES} />)
    const lowBarrierRow = MOCK_ROWS.find(r => r.y_score <= 2)
    const highBarrierRow = MOCK_ROWS.find(r => r.y_score >= 4)
    if (lowBarrierRow) expect(screen.getByText('低')).toBeDefined()
    if (highBarrierRow) expect(screen.getByText('高')).toBeDefined()
  })

  it('renders x_score as colored circle badge', () => {
    render(<ScoreTable rows={MOCK_ROWS} axes={MOCK_AXES} />)
    const firstRow = MOCK_ROWS[0]
    const scoreText = screen.getAllByText(String(firstRow.x_score))
    const badge = scoreText.find(el => el.classList.contains('rounded-full'))
    expect(badge).toBeDefined()
  })

  it('calls onRowClick when row is clicked', async () => {
    const { default: userEvent } = await import('@testing-library/user-event')
    const user = userEvent.setup()
    const handleClick = vi.fn()
    render(<ScoreTable rows={MOCK_ROWS} axes={MOCK_AXES} onRowClick={handleClick} />)
    await user.click(screen.getByText(MOCK_ROWS[0].name))
    expect(handleClick).toHaveBeenCalledWith(expect.objectContaining({ persona_id: MOCK_ROWS[0].persona_id }))
  })
})
