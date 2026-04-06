import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'
import { useStore } from '../store'

// jsdom does not implement ResizeObserver — provide a no-op mock
globalThis.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}))

const initialStoreState = useStore.getState()

afterEach(() => {
  cleanup()
  useStore.setState(initialStoreState, true)
})
