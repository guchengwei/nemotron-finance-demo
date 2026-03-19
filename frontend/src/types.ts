export interface FinancialExtension {
  financial_literacy?: string
  investment_experience?: string
  financial_concerns?: string
  annual_income_bracket?: string
  asset_bracket?: string
  primary_bank_type?: string
}

export interface Persona {
  uuid: string
  name: string
  age: number
  sex: string
  prefecture: string
  region: string
  area?: string
  occupation: string
  education_level: string
  marital_status: string
  persona: string
  professional_persona: string
  sports_persona?: string
  arts_persona?: string
  travel_persona?: string
  culinary_persona?: string
  cultural_background: string
  skills_and_expertise: string
  skills_and_expertise_list?: string
  hobbies_and_interests: string
  hobbies_and_interests_list?: string
  career_goals_and_ambitions: string
  country?: string
  financial_extension?: FinancialExtension
}

export interface FiltersResponse {
  sex: string[]
  age_ranges: string[]
  regions: string[]
  prefectures: string[]
  occupations_top50: string[]
  education_levels: string[]
  total_count: number
}

export interface CountResponse {
  total_matching: number
}

export interface PersonaSample {
  total_matching: number
  sampled: Persona[]
}

export interface SurveyRunRequest {
  persona_ids: string[]
  survey_theme: string
  questions?: string[]
  label?: string
  enable_thinking?: boolean
}

export interface TopPick {
  persona_uuid: string
  persona_name: string
  persona_summary: string
  highlight_reason: string
  highlight_quote: string
}

export interface ReportResponse {
  run_id: string
  overall_score?: number
  score_distribution?: Record<string, number>
  group_tendency?: string
  conclusion?: string
  top_picks?: TopPick[]
  demographic_breakdown?: {
    by_age?: Record<string, number>
    by_sex?: Record<string, number>
    by_financial_literacy?: Record<string, number>
  }
}

export interface SurveyRunSummary {
  id: string
  created_at: string
  label?: string
  survey_theme: string
  persona_count: number
  status: string
  overall_score?: number
}

export interface HistoryListResponse {
  runs: SurveyRunSummary[]
}

export interface SurveyAnswer {
  persona_uuid: string
  persona_summary: string
  persona_full_json: string
  question_index: number
  question_text: string
  answer: string
  score?: number
}

export interface SurveyRunDetail {
  id: string
  created_at: string
  label?: string
  survey_theme: string
  questions: string[]
  filter_config?: Record<string, unknown>
  persona_count: number
  status: string
  report?: ReportResponse
  answers: SurveyAnswer[]
  followup_chats: Record<string, Array<{ role: string; content: string }>>
  enable_thinking?: boolean
}

export interface SSERunCreated {
  run_id: string
  total_personas: number
}

export interface SSEQuestionsGenerated {
  questions: string[]
}

export interface SSEPersonaStart {
  persona_uuid: string
  name: string
  index: number
  total: number
}

export interface SSEPersonaAnswerChunk {
  persona_uuid: string
  question_index: number
  chunk: string
}

export interface SSEPersonaThinking {
  persona_uuid: string
  question_index: number
  thinking: string
}

export interface SSEPersonaAnswer {
  persona_uuid: string
  question_index: number
  answer: string
  score?: number
  thinking?: string
}

export interface SSEPersonaComplete {
  persona_uuid: string
  index: number
}

export interface SSESurveyComplete {
  run_id: string
  completed: number
  failed: number
}

export type PersonaStatus = 'waiting' | 'active' | 'complete' | 'error'

export interface PersonaRunState {
  persona: Persona
  status: PersonaStatus
  answers: Array<{ question: string; answer: string; score?: number; thinking?: string }>
  activeQuestion?: number
  activeAnswer?: string
  activeThinking?: string
}
