/** Extract 【評価: X】score from answer text. Returns 1-5 or null. */
export function parseScore(text: string): number | null {
  const m1 = text.match(/【評価[:：]\s*(\d)】/)
  if (m1) {
    const n = parseInt(m1[1])
    if (n >= 1 && n <= 5) return n
  }
  const m2 = text.trimStart().match(/^(\d)\s*[。、.:/／]/)
  if (m2) {
    const n = parseInt(m2[1])
    if (n >= 1 && n <= 5) return n
  }
  return null
}

export function scoreColor(score: number): string {
  switch (score) {
    case 1: return '#ef4444'  // red
    case 2: return '#f97316'  // orange
    case 3: return '#eab308'  // yellow
    case 4: return '#86efac'  // light green
    case 5: return '#2563EB'  // nvidia green
    default: return '#888'
  }
}

export function scoreBg(score: number): string {
  switch (score) {
    case 1: return 'bg-red-600'
    case 2: return 'bg-orange-500'
    case 3: return 'bg-yellow-500'
    case 4: return 'bg-green-400'
    case 5: return 'bg-[#2563EB]'
    default: return 'bg-gray-600'
  }
}
