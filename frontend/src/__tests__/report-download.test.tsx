import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ReportDashboard from '../components/ReportDashboard'
import { useStore } from '../store'

vi.mock('../api', () => ({
  api: { generateReport: vi.fn() },
}))

vi.mock('../components/DemographicCharts', () => ({
  default: () => <div data-testid="demographic-charts" />,
}))

vi.mock('../components/report-matrix/MatrixReport', () => ({
  default: () => <div data-testid="matrix-report" />,
}))

function setupStore() {
  useStore.setState({
    currentReport: {
      run_id: 'test-run-001',
      overall_score: 3.5,
      group_tendency: 'テスト傾向',
      top_picks: [],
    },
    currentRunId: 'test-run-001',
    currentHistoryRun: null,
    selectedPersonas: [],
    surveyTheme: 'テストテーマ',
    matrixReport: {
      status: 'complete',
      axes: {
        x_axis: { name: '関心度', rubric: '', label_low: '', label_high: '' },
        y_axis: { name: '障壁', rubric: '', label_low: '', label_high: '' },
        quadrants: [],
      },
      personas: [{
        persona_id: 'p1', name: '田中', x_score: 3, y_score: 2,
        keywords: [], quadrant_label: '即時採用層', industry: '小売', age: 40,
      }],
      keywords: { strengths: [], weaknesses: [] },
      recommendations: [],
      scoreTable: [],
      errorMessage: '',
    },
  })
}

afterEach(() => {
  useStore.getState().resetSurvey()
  vi.restoreAllMocks()
})

describe('ReportDashboard download button', () => {
  it('shows matrix-specific label when matrix tab is active', () => {
    setupStore()
    render(<ReportDashboard />)
    // Matrix tab is the default
    expect(screen.getByRole('button', { name: /マトリクス JSON/ })).toBeDefined()
  })

  it('shows text-report label when text tab is active', async () => {
    setupStore()
    const user = userEvent.setup()
    render(<ReportDashboard />)
    await user.click(screen.getByText('テキストレポート'))
    expect(screen.getByRole('button', { name: /レポート JSON/ })).toBeDefined()
  })

  it('downloads matrix data as JSON when on matrix tab', () => {
    setupStore()
    // Spy on Blob constructor to capture what data is serialized
    const blobSpy = vi.fn()
    const OrigBlob = globalThis.Blob
    globalThis.Blob = class extends OrigBlob {
      constructor(parts?: BlobPart[], options?: BlobPropertyBag) {
        super(parts, options)
        blobSpy(parts, options)
      }
    } as typeof Blob
    URL.createObjectURL = vi.fn().mockReturnValue('blob:mock')
    URL.revokeObjectURL = vi.fn()

    render(<ReportDashboard />)
    // Default tab is matrix
    fireEvent.click(screen.getByRole('button', { name: /マトリクス JSON/ }))

    expect(blobSpy).toHaveBeenCalledTimes(1)
    const jsonStr = blobSpy.mock.calls[0][0][0] as string
    const parsed = JSON.parse(jsonStr)
    expect(parsed.axes).toBeDefined()
    expect(parsed.personas).toHaveLength(1)
    expect(parsed.personas[0].name).toBe('田中')

    globalThis.Blob = OrigBlob
  })

  it('downloads text report data as JSON when on text tab', async () => {
    setupStore()
    const blobSpy = vi.fn()
    const OrigBlob = globalThis.Blob
    globalThis.Blob = class extends OrigBlob {
      constructor(parts?: BlobPart[], options?: BlobPropertyBag) {
        super(parts, options)
        blobSpy(parts, options)
      }
    } as typeof Blob
    URL.createObjectURL = vi.fn().mockReturnValue('blob:mock')
    URL.revokeObjectURL = vi.fn()

    const user = userEvent.setup()
    render(<ReportDashboard />)
    await user.click(screen.getByText('テキストレポート'))
    await user.click(screen.getByRole('button', { name: /レポート JSON/ }))

    expect(blobSpy).toHaveBeenCalledTimes(1)
    const jsonStr = blobSpy.mock.calls[0][0][0] as string
    const parsed = JSON.parse(jsonStr)
    expect(parsed.run_id).toBe('test-run-001')
    expect(parsed.overall_score).toBe(3.5)
    // Should NOT contain matrix fields
    expect(parsed.axes).toBeUndefined()

    globalThis.Blob = OrigBlob
  })
})
