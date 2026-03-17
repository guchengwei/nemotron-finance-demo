import { useEffect, useRef } from 'react'

export function useSSECleanup(cleanup: (() => void) | null) {
  const ref = useRef(cleanup)
  ref.current = cleanup

  useEffect(() => {
    return () => {
      ref.current?.()
    }
  }, [])
}
