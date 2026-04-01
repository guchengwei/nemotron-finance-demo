export interface AxisDef {
  name: string
  rubric: string
  label_low: string
  label_high: string
}

export interface QuadrantDef {
  position: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right'
  label: string
  subtitle: string
}

export interface AxisConfig {
  x_axis: AxisDef
  y_axis: AxisDef
  quadrants: QuadrantDef[]
}

export interface KeywordEntry {
  text: string
  polarity: 'strength' | 'weakness'
}

export interface ScoredPersona {
  persona_id: string
  name: string
  x_score: number
  y_score: number
  x_score_raw?: number
  y_score_raw?: number
  keywords: KeywordEntry[]
  quadrant_label: string
  industry: string
  age: number
}

export interface AggregatedKeyword {
  text: string
  polarity: 'strength' | 'weakness'
  count: number
  elaboration: string
  persona_names: string[]
}

export interface KeywordSummary {
  strengths: AggregatedKeyword[]
  weaknesses: AggregatedKeyword[]
}

export interface Recommendation {
  title: string
  highlight_tag: string
  body: string
}

export interface ScoreTableRow {
  persona_id: string
  name: string
  x_score: number
  y_score: number
  x_score_raw?: number
  y_score_raw?: number
  industry: string
  age: number
  quadrant_label: string
}

export interface MatrixReportState {
  axes: AxisConfig | null
  personas: ScoredPersona[]
  keywords: KeywordSummary | null
  recommendations: Recommendation[]
  scoreTable: ScoreTableRow[]
  status: 'idle' | 'streaming' | 'complete' | 'error'
  errorMessage: string
}
