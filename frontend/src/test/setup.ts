import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'
import { useStore } from '../store'

const initialStoreState = useStore.getState()

afterEach(() => {
  cleanup()
  useStore.setState(initialStoreState, true)
})
