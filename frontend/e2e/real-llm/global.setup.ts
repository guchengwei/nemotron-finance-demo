import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

async function waitForReady(url: string, timeoutMs: number) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch {
      // ignore and retry
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000))
  }
  throw new Error(`Timed out waiting for ${url}`)
}

export default async function globalSetup() {
  const backendBase = 'http://127.0.0.1:8180'

  await waitForReady(`${backendBase}/ready`, 10 * 60 * 1000)

  const healthResponse = await fetch(`${backendBase}/health`)
  if (!healthResponse.ok) {
    throw new Error(`/health failed with ${healthResponse.status}`)
  }

  const health = await healthResponse.json() as { mock_llm: boolean; llm_reachable: boolean }
  if (health.mock_llm) {
    throw new Error('Real-LLM E2E requires MOCK_LLM=false, but /health reported mock_llm=true')
  }
  if (!health.llm_reachable) {
    throw new Error('Real-LLM E2E requires a reachable local LLM server, but /health reported llm_reachable=false')
  }

  execFileSync(
    process.env.PYTHON || 'python3',
    [
      path.resolve(__dirname, '../../../backend/scripts/seed_e2e_history.py'),
      '--backend-url',
      backendBase,
      '--history-db',
      path.resolve(__dirname, '../../../data/e2e-history.db'),
    ],
    {
      cwd: path.resolve(__dirname, '../../'),
      stdio: 'inherit',
    },
  )
}
