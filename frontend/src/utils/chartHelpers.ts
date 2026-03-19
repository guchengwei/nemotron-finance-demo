/** Format recharts data from demographic breakdown. */

export function formatAgeData(byAge: Record<string, number>) {
  const order = ['20-39', '40-59', '60+']
  return order
    .filter((k) => k in byAge)
    .map((k) => ({ name: k, score: byAge[k] }))
}

export function formatSexData(bySex: Record<string, number>) {
  return Object.entries(bySex).map(([name, score]) => ({ name, score }))
}

export function formatLiteracyData(byLit: Record<string, number>) {
  const order = ['初心者', '中級者', '上級者', '専門家']
  return order
    .filter((k) => k in byLit)
    .map((k) => ({ name: k, score: byLit[k] }))
}

export function formatScoreDistribution(dist: Record<string, number>) {
  return [1, 2, 3, 4, 5].map((s) => ({
    name: `${s}点`,
    count: dist[String(s)] || 0,
  }))
}

export const CHART_COLORS = ['#1F6A5A', '#4C7B62', '#8F7B56', '#B58A57', '#D1B38A']
