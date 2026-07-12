import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, observeSurvey } from './api'

describe('startup API helpers', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('checkReady fails closed when a 200 response returns HTML', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('<!doctype html>', {
        status: 200,
        headers: { 'Content-Type': 'text/html' },
      }),
    )

    await expect(api.checkReady()).resolves.toEqual({ ready: false })
  })

  it('checkReady returns ready only for the expected JSON payload', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ status: 'ready' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await expect(api.checkReady()).resolves.toEqual({ ready: true })
  })

  it('checkHealth rejects non-JSON responses with a controlled error', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('<!doctype html>', {
        status: 200,
        headers: { 'Content-Type': 'text/html' },
      }),
    )

    await expect(api.checkHealth()).rejects.toThrow('GET /health returned non-JSON')
  })
})

describe('cancel and delete orchestration', () => {
  it('does not delete until the survey_cancelled event is delivered', async () => {
    const listeners = new Map<string, (event: MessageEvent<string>) => void>()
    class FakeEventSource {
      onopen = null
      onerror = null
      addEventListener(name: string, listener: EventListener) {
        listeners.set(name, listener as (event: MessageEvent<string>) => void)
      }
      close() {}
    }
    vi.stubGlobal('EventSource', FakeEventSource)
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'cancellation_pending' }), {
        status: 202, headers: { 'Content-Type': 'application/json' },
      }))
      .mockResolvedValueOnce(new Response(null, { status: 200 }))

    const operation = api.cancelAndDeleteSurvey('run-1')
    await Promise.resolve()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    listeners.get('survey_cancelled')?.(new MessageEvent('survey_cancelled', {
      data: JSON.stringify({ run_id: 'run-1' }), lastEventId: '4',
    }))
    await operation
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[1][0]).toBe('/api/history/run-1')
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: 'DELETE' })
    vi.unstubAllGlobals()
  })
})

describe('survey observer connection state', () => {
  it('reports reconnecting, live, and disconnected separately', () => {
    let instance: any
    class FakeEventSource {
      onopen: (() => void) | null = null
      onerror: (() => void) | null = null
      constructor() { instance = this }
      addEventListener() {}
      close() {}
    }
    vi.stubGlobal('EventSource', FakeEventSource)
    const states: string[] = []
    const close = observeSurvey('run-1', vi.fn(), vi.fn(), (state) => states.push(state))
    instance.onopen()
    instance.onerror()
    close()
    expect(states).toEqual(['reconnecting', 'live', 'reconnecting', 'disconnected'])
    vi.unstubAllGlobals()
  })
})
