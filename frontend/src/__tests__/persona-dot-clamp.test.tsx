import { describe, it, expect } from 'vitest'
import { clampOffset } from '../components/report-matrix/PersonaDot'

describe('clampOffset', () => {
  // score=3 → center at 50% = 300px. Room in either direction = 300 - 20 = 280px.
  // Any reasonable offset fits.
  it('does not reduce offset when dot is centered (score=3)', () => {
    expect(clampOffset(20, 3, 600)).toBe(20)
    expect(clampOffset(-20, 3, 600)).toBe(-20)
    expect(clampOffset(28, 3, 600)).toBe(28)
  })

  // score=1 → center at 5% = 30px. Room to the left = 30 - 20 = 10px.
  // A negative offset of -20 should be clamped.
  it('reduces negative offset when dot is near left edge (score=1)', () => {
    const result = clampOffset(-20, 1, 600)
    expect(result).toBeGreaterThan(-20) // clamped toward 0
    expect(result).toBeLessThan(0) // still negative direction
  })

  // score=1, positive offset pushes rightward (away from left edge). Plenty of room. No clamp.
  it('allows positive offset when dot is near left edge (pushes toward center)', () => {
    expect(clampOffset(20, 1, 600)).toBe(20)
  })

  // score=5 → center at 95% = 570px. Room to the right = 600 - 570 - 20 = 10px.
  // A positive offset of 20 should be clamped.
  it('reduces positive offset when dot is near right edge (score=5)', () => {
    const result = clampOffset(20, 5, 600)
    expect(result).toBeLessThan(20) // clamped
    expect(result).toBeGreaterThan(0) // still positive direction
  })

  // score=5, negative offset pushes leftward (away from right edge). Plenty of room. No clamp.
  it('allows negative offset when dot is near right edge (pushes toward center)', () => {
    expect(clampOffset(-20, 5, 600)).toBe(-20)
  })

  it('returns 0 for 0 offset regardless of position', () => {
    expect(clampOffset(0, 1, 600)).toBe(0)
    expect(clampOffset(0, 3, 600)).toBe(0)
    expect(clampOffset(0, 5, 600)).toBe(0)
  })

  it('returns 0 when containerSize is 0', () => {
    expect(clampOffset(20, 3, 0)).toBe(0)
  })
})
