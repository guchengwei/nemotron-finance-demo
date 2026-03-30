import { create } from 'zustand'
import type {
  Persona,
  PersonaRunState,
  ReportResponse,
  SurveyRunSummary,
  SurveyRunDetail,
  FiltersResponse,
} from './types'
import type { MatrixReportState } from './types/matrix-report'
import { DEFAULT_SURVEY_QUESTIONS } from './config/surveyPresets'

export type Step = 1 | 2 | 3 | 4 | 5

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
  appendFollowupMessages: (personaUuid: string, messages: Array<{ role: string; content: string }>) => void
  clearFollowupMessages: (personaUuid: string) => void

  dbReady: boolean
  setDbReady: (ready: boolean) => void
  llmStatus: { mock_llm: boolean; llm_reachable: boolean } | null
  setLlmStatus: (status: { mock_llm: boolean; llm_reachable: boolean }) => void

  enableThinking: boolean
  setEnableThinking: (v: boolean) => void

  activeDetailPersona: import('./types').Persona | null
  openPersonaDetail: (p: import('./types').Persona) => void
  closePersonaDetail: () => void

  matrixReport: MatrixReportState
  setMatrixReport: (update: Partial<MatrixReportState>) => void

  resetVersion: number
  resetSurvey: () => void
}

export const useStore = create<AppState>((set) => ({
  currentStep: 1,
  setStep: (step) => set({ currentStep: step }),

  filters: null,
  setFilters: (filters) => set({ filters }),
  selectedPersonas: [],
  setSelectedPersonas: (selectedPersonas) => set({ selectedPersonas }),

  surveyTheme: '',
  setSurveyTheme: (surveyTheme) => set({ surveyTheme }),
  questions: DEFAULT_SURVEY_QUESTIONS,
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
  appendFollowupMessages: (personaUuid, messages) =>
    set((state) => {
      if (!state.currentHistoryRun) return state
      const existing = state.currentHistoryRun.followup_chats[personaUuid] || []
      return {
        currentHistoryRun: {
          ...state.currentHistoryRun,
          followup_chats: {
            ...state.currentHistoryRun.followup_chats,
            [personaUuid]: [...existing, ...messages],
          },
        },
      }
    }),
  clearFollowupMessages: (personaUuid) =>
    set((state) => {
      if (!state.currentHistoryRun) return state
      return {
        currentHistoryRun: {
          ...state.currentHistoryRun,
          followup_chats: {
            ...state.currentHistoryRun.followup_chats,
            [personaUuid]: [],
          },
        },
      }
    }),

  dbReady: false,
  setDbReady: (dbReady) => set({ dbReady }),
  llmStatus: null,
  setLlmStatus: (llmStatus) => set({ llmStatus }),

  enableThinking: false,
  setEnableThinking: (enableThinking) => set({ enableThinking }),

  activeDetailPersona: null,
  openPersonaDetail: (activeDetailPersona) => set({ activeDetailPersona }),
  closePersonaDetail: () => set({ activeDetailPersona: null }),

  matrixReport: {
    axes: null,
    personas: [],
    keywords: null,
    recommendations: [],
    scoreTable: [],
    status: 'idle',
    errorMessage: '',
  },
  setMatrixReport: (update) =>
    set((s) => ({ matrixReport: { ...s.matrixReport, ...update } })),

  resetVersion: 0,
  resetSurvey: () =>
    set((state) => ({
      currentStep: 1,
      filters: null,
      selectedPersonas: [],
      surveyTheme: '',
      questions: DEFAULT_SURVEY_QUESTIONS,
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
