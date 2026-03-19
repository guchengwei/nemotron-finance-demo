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
    case 1: return '#A14B45'
    case 2: return '#A86A32'
    case 3: return '#B58A57'
    case 4: return '#3F7A5D'
    case 5: return '#1F6A5A'
    default: return '#70685C'
  }
}

export function scoreBg(score: number): string {
  switch (score) {
    case 1: return 'bg-fin-danger'
    case 2: return 'bg-fin-warning'
    case 3: return 'bg-fin-bronze'
    case 4: return 'bg-fin-success'
    case 5: return 'bg-fin-accent'
    default: return 'bg-fin-muted'
  }
}
