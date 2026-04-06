import { useMemo } from 'react'
import type { AxisConfig, ScoredPersona } from '../../types/matrix-report'
import { CHART_COLORS } from '../../utils/chartHelpers'
import PersonaDot from './PersonaDot'

const QUADRANT_BG: Record<string, string> = {
  'top-left':     'bg-slate-50',
  'top-right':    'bg-amber-50',
  'bottom-left':  'bg-white',
  'bottom-right': 'bg-green-50',
}

const SUNFLOWER_SPREAD = 20
const GOLDEN_ANGLE = 2.399963 // radians

export function computeSunflowerOffsets(personas: ScoredPersona[]): Map<string, { dx: number; dy: number }> {
  // Group personas by coordinate key
  const groups = new Map<string, ScoredPersona[]>()
  for (const p of personas) {
    const key = `${p.x_score},${p.y_score}`
    const group = groups.get(key) || []
    group.push(p)
    groups.set(key, group)
  }

  const result = new Map<string, { dx: number; dy: number }>()
  for (const group of groups.values()) {
    if (group.length === 1) {
      result.set(group[0].persona_id, { dx: 0, dy: 0 })
    } else {
      // Persona 0 at center, rest at sunflower positions
      result.set(group[0].persona_id, { dx: 0, dy: 0 })
      for (let i = 1; i < group.length; i++) {
        const angle = i * GOLDEN_ANGLE
        const radius = SUNFLOWER_SPREAD * Math.sqrt(i)
        result.set(group[i].persona_id, {
          dx: radius * Math.cos(angle),
          dy: radius * Math.sin(angle),
        })
      }
    }
  }
  return result
}

interface QuadrantMatrixProps {
  axes: AxisConfig
  personas: ScoredPersona[]
  onPersonaClick?: (persona: ScoredPersona) => void
}

export default function QuadrantMatrix({ axes, personas, onPersonaClick }: QuadrantMatrixProps) {
  const getColor = useMemo(() => {
    const counts = new Map<string, number>()
    for (const p of personas) {
      counts.set(p.industry, (counts.get(p.industry) || 0) + 1)
    }
    const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([name]) => name)
    const colorMap = new Map(sorted.map((name, i) => [name, CHART_COLORS[i % CHART_COLORS.length]]))
    return (industry: string) => colorMap.get(industry) || CHART_COLORS[0]
  }, [personas])

  const offsets = useMemo(() => computeSunflowerOffsets(personas), [personas])

  return (
    <div className="space-y-3">
      <div className="rounded-[1.75rem] border border-fin-border bg-fin-surface p-6 shadow-card">
        {/* X-axis label */}
        <div className="mb-2 text-center text-xs font-semibold text-fin-accent">
          {axes.x_axis.name}
        </div>

        <div className="flex items-center gap-2">
          {/* Y-axis label + endpoint labels */}
          <div className="flex flex-col items-center gap-1">
            <div className="text-[10px] text-gray-400">↑ {axes.y_axis.label_high}</div>
            <div className="text-xs font-semibold text-fin-accent" style={{ writingMode: 'vertical-rl' }}>
              {axes.y_axis.name}
            </div>
            <div className="text-[10px] text-gray-400">↓ {axes.y_axis.label_low}</div>
          </div>

          {/* Matrix plot */}
          <div className="relative w-full" style={{ paddingBottom: '100%' }}>
            <div className="absolute inset-0">
              {/* Quadrant backgrounds */}
              {axes.quadrants.map((q) => {
                const isTop = q.position.startsWith('top')
                const isLeft = q.position.endsWith('left')
                return (
                  <div
                    key={q.position}
                    className={`absolute h-1/2 w-1/2 ${QUADRANT_BG[q.position]}`}
                    style={{ top: isTop ? 0 : '50%', left: isLeft ? 0 : '50%' }}
                  >
                    <div className="absolute left-3 top-2">
                      <div className="text-xs font-bold">{q.label}</div>
                      <div className="text-[10px] opacity-60">{q.subtitle}</div>
                    </div>
                  </div>
                )
              })}

              {/* Axis dividers */}
              <div className="absolute left-1/2 top-0 h-full w-px bg-gray-200" />
              <div className="absolute left-0 top-1/2 h-px w-full bg-gray-200" />

              {/* Persona dots */}
              {personas.map((p, i) => (
                <PersonaDot
                  key={p.persona_id}
                  persona={p}
                  color={getColor(p.industry)}
                  index={i}
                  offset={offsets.get(p.persona_id) || { dx: 0, dy: 0 }}
                  onClick={onPersonaClick}
                />
              ))}
            </div>
          </div>
        </div>

        {/* Axis endpoint labels */}
        <div className="mt-1 flex justify-between text-[10px] text-gray-400">
          <span>← {axes.x_axis.label_low}</span>
          <span>{axes.x_axis.label_high} →</span>
        </div>
      </div>

    </div>
  )
}
