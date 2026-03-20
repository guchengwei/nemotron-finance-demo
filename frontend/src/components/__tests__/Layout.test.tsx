import { act, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import Layout from '../Layout'
import { useStore } from '../../store'

vi.mock('../Sidebar', () => ({
  default: () => <div data-testid="sidebar" />,
}))

vi.mock('../StepIndicator', () => ({
  default: () => <div data-testid="step-indicator" />,
}))

vi.mock('../PersonaDetailModal', () => ({
  default: () => null,
}))

describe('Layout', () => {
  it('makes main container own overflow only outside step 5', () => {
    const { container, rerender } = render(
      <Layout>
        <div>content</div>
      </Layout>,
    )

    const shell = container.firstElementChild
    const main = container.querySelector('main')

    expect(shell).toHaveClass('h-dvh')
    expect(main).toHaveClass('min-h-0')
    expect(main).toHaveClass('overflow-auto')

    act(() => {
      useStore.setState({ currentStep: 5 })
    })
    rerender(
      <Layout>
        <div>content</div>
      </Layout>,
    )

    expect(main).toHaveClass('overflow-hidden')
  })
})
