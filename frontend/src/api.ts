import type {
  CountResponse,
  FiltersResponse,
  PersonaSample,
  SurveyRunRequest,
  ReportResponse,
  HistoryListResponse,
  SurveyRunDetail,
} from './types'

const BASE = '/api'

async function get<T>(
  path: string,
  params?: Record<string, string | number | undefined>,
  signal?: AbortSignal,
): Promise<T> {
  const url = new URL(BASE + path, window.location.origin)
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') {
        url.searchParams.set(k, String(v))
      }
    })
  }
  const res = await fetch(url.toString(), { signal })
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`)
  return res.json()
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`)
  return res.json()
}

async function del(path: string): Promise<void> {
  const res = await fetch(BASE + path, { method: 'DELETE' })
  if (!res.ok) throw new Error(`DELETE ${path} failed: ${res.status}`)
}

type PersonaQueryParams = {
  sex?: string
  age_min?: number
  age_max?: number
  prefecture?: string
  region?: string
  occupation?: string
  education?: string
  financial_literacy?: string
}

export const api = {
  getFilters: (): Promise<FiltersResponse> => get('/personas/filters'),

  getCount: (
    params: PersonaQueryParams,
    signal?: AbortSignal,
  ): Promise<CountResponse> => get('/personas/count', params as Record<string, string | number | undefined>, signal),

  getSample: (
    params: PersonaQueryParams & { count?: number },
    signal?: AbortSignal,
  ): Promise<PersonaSample> => get('/personas/sample', params as Record<string, string | number | undefined>, signal),

  generateReport: (run_id: string): Promise<ReportResponse> =>
    post('/report/generate', { run_id }),

  getHistory: (): Promise<HistoryListResponse> => get('/history'),

  getHistoryRun: (run_id: string): Promise<SurveyRunDetail> => get(`/history/${run_id}`),

  deleteHistoryRun: (run_id: string): Promise<void> => del(`/history/${run_id}`),
}

export function startSurveySSE(
  request: SurveyRunRequest,
  onEvent: (event: string, data: unknown) => void,
  onError: (err: Error) => void,
): () => void {
  let aborted = false
  const controller = new AbortController()

  fetch('/api/survey/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal: controller.signal,
  }).then(async (res) => {
    if (!res.ok || !res.body) {
      onError(new Error(`Survey run failed: ${res.status}`))
      return
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (!aborted) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      let currentEvent = ''
      let currentData = ''

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          currentData = line.slice(6).trim()
        } else if (line === '' && currentEvent && currentData) {
          try {
            const parsed = JSON.parse(currentData)
            onEvent(currentEvent, parsed)
          } catch {
            // skip malformed
          }
          currentEvent = ''
          currentData = ''
        }
      }
    }
  }).catch((err) => {
    if (!aborted) onError(err)
  })

  return () => {
    aborted = true
    controller.abort()
  }
}

export function startFollowupSSE(
  request: { run_id: string; persona_uuid: string; question: string },
  onToken: (text: string) => void,
  onDone: (full_answer: string) => void,
  onError: (err: Error) => void,
  onThinking?: (thinking: string) => void,
): () => void {
  let aborted = false
  const controller = new AbortController()

  fetch('/api/followup/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal: controller.signal,
  }).then(async (res) => {
    if (!res.ok || !res.body) {
      onError(new Error(`Followup failed: ${res.status}`))
      return
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (!aborted) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      let currentEvent = ''
      let currentData = ''

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          currentData = line.slice(6).trim()
        } else if (line === '' && currentEvent && currentData) {
          try {
            const parsed = JSON.parse(currentData)
            if (currentEvent === 'token') onToken(parsed.text)
            if (currentEvent === 'done') onDone(parsed.full_answer)
            if (currentEvent === 'thinking') onThinking?.(parsed.thinking)
          } catch {
            // skip
          }
          currentEvent = ''
          currentData = ''
        }
      }
    }
  }).catch((err) => {
    if (!aborted) onError(err)
  })

  return () => {
    aborted = true
    controller.abort()
  }
}
