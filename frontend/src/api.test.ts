import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

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
