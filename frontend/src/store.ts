import { create } from 'zustand'
import type {
  Persona,
  PersonaRunState,
  ReportResponse,
  SurveyRunSummary,
  SurveyRunDetail,
  FiltersResponse,
} from './types'

export type Step = 1 | 2 | 3 | 4 | 5

export const SURVEY_PRESETS = [
  {
    id: 'ai-advisory',
    name: 'AI資産運用アドバイザリー',
    theme: 'AIを活用した資産運用アドバイザリーサービスの導入に対する金融機関顧客の反応',
    questions: [
      'AIによる資産運用アドバイスをどの程度信頼できると思いますか？（1:全く信頼できない〜5:非常に信頼できる）',
      'AIアドバイザーに期待する主な機能を教えてください',
      '人間のFPとAIアドバイザーをどのように使い分けたいですか？',
      'セキュリティや個人情報保護についての懸念をお聞かせください',
    ],
  },
  {
    id: 'online-fund',
    name: 'オンライン投資信託販売',
    theme: '投資信託のオンライン販売プラットフォームに対する関心度と懸念点',
    questions: [
      'このようなサービスに対する全体的な関心度を教えてください（1:全く関心がない〜5:非常に関心がある）',
      '最も重要だと考える機能や特徴は何ですか？',
      '利用にあたって最も懸念される点は何ですか？',
      '料金体系についてどのようにお考えですか？',
    ],
  },
  {
    id: 'digital-banking',
    name: 'デジタルバンキング',
    theme: 'デジタル銀行サービスの利便性と若年層の金融リテラシー向上への活用',
    questions: [
      'デジタル専業銀行のサービスにどの程度関心がありますか？（1:全く関心がない〜5:非常に関心がある）',
      '既存の銀行と比較して魅力的だと思う点は何ですか？',
      '利用を躊躇する理由があれば教えてください',
    ],
  },
]

interface AppState {
  currentStep: Step
  setStep: (step: Step) => void

  filters: FiltersResponse | null
  setFilters: (f: FiltersResponse) => void
  selectedPersonas: Persona[]
  setSelectedPersonas: (p: Persona[]) => void

  surveyTheme: string
  setSurveyTheme: (t: string) => void
  questions: string[]
  setQuestions: (q: string[]) => void
  surveyLabel: string
  setSurveyLabel: (l: string) => void

  currentRunId: string | null
  setCurrentRunId: (id: string | null) => void
  personaStates: Record<string, PersonaRunState>
  setPersonaStates: (states: Record<string, PersonaRunState>) => void
  setPersonaState: (uuid: string, state: PersonaRunState) => void
  updatePersonaState: (uuid: string, update: Partial<PersonaRunState>) => void
  surveyComplete: boolean
  setSurveyComplete: (v: boolean) => void
  surveyCompleted: number
  surveyFailed: number
  setSurveyCounts: (completed: number, failed: number) => void

  currentReport: ReportResponse | null
  setCurrentReport: (r: ReportResponse | null) => void

  followupPersona: Persona | null
  setFollowupPersona: (p: Persona | null) => void

  history: SurveyRunSummary[]
  setHistory: (h: SurveyRunSummary[]) => void
  currentHistoryRun: SurveyRunDetail | null
  setCurrentHistoryRun: (r: SurveyRunDetail | null) => void

  dbReady: boolean
  setDbReady: (ready: boolean) => void
  llmStatus: { mock_llm: boolean; llm_reachable: boolean } | null
  setLlmStatus: (status: { mock_llm: boolean; llm_reachable: boolean }) => void

  enableThinking: boolean
  setEnableThinking: (v: boolean) => void

  activeDetailPersona: import('./types').Persona | null
  openPersonaDetail: (p: import('./types').Persona) => void
  closePersonaDetail: () => void

  resetVersion: number
  resetSurvey: () => void
}

const defaultQuestions = [
  'このようなサービスに対する全体的な関心度を教えてください（1:全く関心がない〜5:非常に関心がある）',
  '最も重視する点は何ですか？',
  '懸念点や改善要望があればお聞かせください',
]

export const useStore = create<AppState>((set) => ({
  currentStep: 1,
  setStep: (step) => set({ currentStep: step }),

  filters: null,
  setFilters: (filters) => set({ filters }),
  selectedPersonas: [],
  setSelectedPersonas: (selectedPersonas) => set({ selectedPersonas }),

  surveyTheme: '',
  setSurveyTheme: (surveyTheme) => set({ surveyTheme }),
  questions: defaultQuestions,
  setQuestions: (questions) => set({ questions }),
  surveyLabel: '',
  setSurveyLabel: (surveyLabel) => set({ surveyLabel }),

  currentRunId: null,
  setCurrentRunId: (currentRunId) => set({ currentRunId }),
  personaStates: {},
  setPersonaStates: (personaStates) => set({ personaStates }),
  setPersonaState: (uuid, state) =>
    set((s) => ({ personaStates: { ...s.personaStates, [uuid]: state } })),
  updatePersonaState: (uuid, update) =>
    set((s) => ({
      personaStates: {
        ...s.personaStates,
        [uuid]: { ...s.personaStates[uuid], ...update },
      },
    })),
  surveyComplete: false,
  setSurveyComplete: (surveyComplete) => set({ surveyComplete }),
  surveyCompleted: 0,
  surveyFailed: 0,
  setSurveyCounts: (surveyCompleted, surveyFailed) => set({ surveyCompleted, surveyFailed }),

  currentReport: null,
  setCurrentReport: (currentReport) => set({ currentReport }),

  followupPersona: null,
  setFollowupPersona: (followupPersona) => set({ followupPersona }),

  history: [],
  setHistory: (history) => set({ history }),
  currentHistoryRun: null,
  setCurrentHistoryRun: (currentHistoryRun) => set({ currentHistoryRun }),

  dbReady: false,
  setDbReady: (dbReady) => set({ dbReady }),
  llmStatus: null,
  setLlmStatus: (llmStatus) => set({ llmStatus }),

  enableThinking: false,
  setEnableThinking: (enableThinking) => set({ enableThinking }),

  activeDetailPersona: null,
  openPersonaDetail: (activeDetailPersona) => set({ activeDetailPersona }),
  closePersonaDetail: () => set({ activeDetailPersona: null }),

  resetVersion: 0,
  resetSurvey: () =>
    set((state) => ({
      currentStep: 1,
      filters: null,
      selectedPersonas: [],
      surveyTheme: '',
      questions: defaultQuestions,
      surveyLabel: '',
      currentRunId: null,
      personaStates: {},
      surveyComplete: false,
      surveyCompleted: 0,
      surveyFailed: 0,
      currentReport: null,
      followupPersona: null,
      currentHistoryRun: null,
      enableThinking: false,
      activeDetailPersona: null,
      resetVersion: state.resetVersion + 1,
    })),
}))
