import { describe, it, expect, beforeEach } from 'vitest'
import { useStore } from '../store'

describe('matrix report store', () => {
  beforeEach(() => {
    // Reset matrixReport to initial state
    useStore.setState({
      matrixReport: {
        axes: null, personas: [], keywords: null,
        recommendations: [], scoreTable: [],
        status: 'idle', errorMessage: '',
      }
    })
  })

  it('initial state has idle status', () => {
    const state = useStore.getState()
    expect(state.matrixReport.status).toBe('idle')
    expect(state.matrixReport.personas).toHaveLength(0)
  })

  it('setMatrixReport merges partial state', () => {
    const { setMatrixReport } = useStore.getState()
    setMatrixReport({ status: 'streaming' })
    expect(useStore.getState().matrixReport.status).toBe('streaming')
    expect(useStore.getState().matrixReport.personas).toHaveLength(0) // not wiped
  })

  it('setMatrixReport can update axes', () => {
    const { setMatrixReport } = useStore.getState()
    const mockAxes = { x_axis: { name: '関心度', rubric: '', label_low: '', label_high: '' },
                       y_axis: { name: '利用障壁', rubric: '', label_low: '', label_high: '' },
                       quadrants: [] }
    setMatrixReport({ axes: mockAxes })
    expect(useStore.getState().matrixReport.axes?.x_axis.name).toBe('関心度')
  })
})
