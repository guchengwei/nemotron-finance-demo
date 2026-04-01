import type {
  CountResponse,
  FiltersResponse,
  PersonaSample,
  SurveyRunRequest,
  ReportResponse,
  HistoryListResponse,
  SurveyRunDetail,
  FollowUpSuggestionResponse,
  FollowUpClearResponse,
} from './types'

const BASE = '/api'

function isJsonResponse(res: Response) {
  return res.headers.get('content-type')?.includes('application/json') ?? false
}

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
}

type SSECallbacks = {
  onEvent: (event: string, data: unknown) => void
  onError: (err: Error) => void
}

function createSSEProcessor({ onEvent, onError }: SSECallbacks) {
  let buffer = ''
  let currentEvent = ''
  let currentData: string[] = []

  const flush = () => {
    if (!currentEvent) return
    try {
      const payload = currentData.join('\n')
      const parsed = payload ? JSON.parse(payload) : null
      onEvent(currentEvent, parsed)
    } catch (error) {
      onError(error instanceof Error ? error : new Error('Malformed SSE payload'))
    }
    currentEvent = ''
    currentData = []
  }

  return {
    push(chunk: string) {
      buffer += chunk
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const rawLine of lines) {
        const line = rawLine.replace(/\r$/, '')
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          currentData.push(line.slice(6))
        } else if (line === '') {
          flush()
        }
      }
    },
    finish() {
      if (buffer) {
        this.push('\n')
      }
      flush()
    },
  }
}

async function streamSSE(
  input: RequestInfo | URL,
  init: RequestInit,
  callbacks: SSECallbacks,
): Promise<void> {
  const res = await fetch(input, init)
  if (!res.ok || !res.body) {
    throw new Error(`SSE request failed: ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  const processor = createSSEProcessor(callbacks)

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    processor.push(decoder.decode(value, { stream: true }))
  }

  processor.finish()
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

  generateQuestions: (survey_theme: string): Promise<{ questions: string[] }> =>
    post('/survey/questions', { survey_theme }),

  generateReport: (run_id: string): Promise<ReportResponse> =>
    post('/report/generate', { run_id }),

  getHistory: (): Promise<HistoryListResponse> => get('/history'),

  getHistoryRun: (run_id: string): Promise<SurveyRunDetail> => get(`/history/${run_id}`),

  getFollowupSuggestions: (
    run_id: string,
    persona_uuid: string,
  ): Promise<FollowUpSuggestionResponse> => post('/followup/suggestions', { run_id, persona_uuid }),

  clearFollowupHistory: (
    run_id: string,
    persona_uuid: string,
  ): Promise<FollowUpClearResponse> => post('/followup/clear', { run_id, persona_uuid }),

  deleteHistoryRun: (run_id: string): Promise<void> => del(`/history/${run_id}`),

  async checkReady(): Promise<{ ready: boolean; error?: string }> {
    try {
      const res = await fetch('/ready')
      if (res.ok) {
        if (!isJsonResponse(res)) return { ready: false }
        const data = await res.json().catch(() => null) as { status?: string } | null
        return data?.status === 'ready' ? { ready: true } : { ready: false }
      }
      if (res.status === 500) {
        if (!isJsonResponse(res)) {
          return { ready: false, error: 'Database initialization failed' }
        }
        const data = await res.json()
        return { ready: false, error: data.detail || 'Database initialization failed' }
      }
      return { ready: false }
    } catch {
      return { ready: false }
    }
  },

  async checkHealth(): Promise<{ status: string; mock_llm: boolean; llm_reachable: boolean }> {
    const res = await fetch('/health')
    if (!res.ok) {
      throw new Error(`GET /health failed: ${res.status}`)
    }
    if (!isJsonResponse(res)) {
      throw new Error('GET /health returned non-JSON')
    }
    const data = await res.json().catch(() => {
      throw new Error('GET /health returned invalid JSON')
    }) as { status?: string; mock_llm?: boolean; llm_reachable?: boolean }
    if (
      typeof data.status !== 'string' ||
      typeof data.mock_llm !== 'boolean' ||
      typeof data.llm_reachable !== 'boolean'
    ) {
      throw new Error('GET /health returned invalid payload')
    }
    return {
      status: data.status,
      mock_llm: data.mock_llm,
      llm_reachable: data.llm_reachable,
    }
  },
}

export function startSurveySSE(
  request: SurveyRunRequest,
  onEvent: (event: string, data: unknown) => void,
  onError: (err: Error) => void,
): () => void {
  let aborted = false
  const controller = new AbortController()

  streamSSE(
    '/api/survey/run',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal: controller.signal,
    },
    {
      onEvent: (event, data) => {
        if (!aborted) onEvent(event, data)
      },
      onError: (err) => {
        if (!aborted) onError(err)
      },
    },
  ).catch((err) => {
    if (!aborted) onError(err instanceof Error ? err : new Error(String(err)))
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

  streamSSE(
    '/api/followup/ask',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal: controller.signal,
    },
    {
      onEvent: (currentEvent, parsed) => {
        if (aborted || !parsed || typeof parsed !== 'object') return
        const data = parsed as Record<string, string>
        if (currentEvent === 'token' && data.text) onToken(data.text)
        if (currentEvent === 'done' && data.full_answer !== undefined) onDone(data.full_answer)
        if (currentEvent === 'thinking' && data.thinking) onThinking?.(data.thinking)
        if (currentEvent === 'error') onError(new Error(data.error || 'Followup stream failed'))
      },
      onError: (err) => {
        if (!aborted) onError(err)
      },
    },
  ).catch((err) => {
    if (!aborted) onError(err instanceof Error ? err : new Error(String(err)))
  })

  return () => {
    aborted = true
    controller.abort()
  }
}

export async function getMatrixReport(surveyId: string): Promise<{
  axes: unknown; personas: unknown[]; keywords: unknown; recommendations: unknown[]
} | null> {
  try {
    const res = await fetch(`/api/report/matrix/${surveyId}`)
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

export function startMatrixReportSSE(
  request: { survey_id: string; preset_key: string },
  onEvent: (event: string, data: unknown) => void,
  onError: (err: Error) => void,
): () => void {
  let aborted = false
  const controller = new AbortController()

  streamSSE(
    '/api/report/matrix',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal: controller.signal,
    },
    {
      onEvent: (event, data) => {
        if (!aborted) onEvent(event, data)
      },
      onError: (err) => {
        if (!aborted) onError(err)
      },
    },
  ).catch((err) => {
    if (!aborted) onError(err instanceof Error ? err : new Error(String(err)))
  })

  return () => {
    aborted = true
    controller.abort()
  }
}
