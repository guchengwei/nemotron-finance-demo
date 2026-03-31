import { useState } from 'react'
import type { ScoredPersona } from '../../types/matrix-report'

interface PersonaDotProps {
  persona: ScoredPersona
  color: string
  index: number
  offset: { dx: number; dy: number }
  onClick?: (persona: ScoredPersona) => void
}

export default function PersonaDot({ persona, color, index, offset, onClick }: PersonaDotProps) {
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
        transform: `translate(calc(-50% + ${offset.dx}px), calc(-50% + ${offset.dy}px))`,
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
