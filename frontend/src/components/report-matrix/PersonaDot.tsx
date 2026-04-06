import { useState } from 'react'
import type { ScoredPersona } from '../../types/matrix-report'

const DOT_RADIUS = 16 // half of h-8 w-8 (32px)

/**
 * Clamp a sunflower offset so the dot stays within the matrix container.
 * offsetPx: raw pixel offset (positive = right/down, negative = left/up)
 * score: axis score 1–5, maps to 5%–95% position
 * containerPx: container width or height in pixels
 */
export function clampOffset(offsetPx: number, score: number, containerPx: number): number {
  if (offsetPx === 0 || containerPx === 0) return 0
  const positionPx = (((score - 1) / 4) * 90 + 5) / 100 * containerPx
  const margin = DOT_RADIUS + 4 // 4px padding from container edge
  const roomLeft = positionPx - margin
  const roomRight = containerPx - positionPx - margin
  const room = offsetPx > 0 ? roomRight : roomLeft
  if (room <= 0) return 0
  const absOffset = Math.abs(offsetPx)
  if (absOffset <= room) return offsetPx
  return Math.sign(offsetPx) * room
}

interface PersonaDotProps {
  persona: ScoredPersona
  color: string
  index: number
  offset: { dx: number; dy: number }
  containerSize: number
  onClick?: (persona: ScoredPersona) => void
}

export default function PersonaDot({ persona, color, index, offset, containerSize, onClick }: PersonaDotProps) {
  const clampedDx = clampOffset(offset.dx, persona.x_score, containerSize)
  const clampedDy = clampOffset(offset.dy, persona.y_score, containerSize)
  const [showTooltip, setShowTooltip] = useState(false)

  // Map 1-5 score to 5%-95% position (inverted Y: high score = top = low CSS top)
  const left = `${((persona.x_score - 1) / 4) * 90 + 5}%`
  const top = `${(1 - (persona.y_score - 1) / 4) * 90 + 5}%`

  return (
    <div
      className="absolute cursor-pointer"
      style={{
        left,
        top,
        animationDelay: `${index * 80}ms`,
        transform: `translate(calc(-50% + ${clampedDx}px), calc(-50% + ${clampedDy}px))`,
      }}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
      onClick={() => onClick?.(persona)}
    >
      <div
        className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-fin-surface text-[9px] font-bold text-fin-surface shadow-sm"
        style={{ backgroundColor: color }}
      >
        {persona.name.slice(0, 2)}
      </div>

      {showTooltip && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 whitespace-nowrap rounded-2xl border border-fin-border bg-fin-surface px-3 py-2 text-xs shadow-card z-10">
          <div className="font-medium text-fin-ink">{persona.name}</div>
          <div className="text-fin-muted">{persona.industry} / {persona.age}歳</div>
          <div className="font-medium text-fin-accent">{persona.quadrant_label}</div>
        </div>
      )}
    </div>
  )
}
