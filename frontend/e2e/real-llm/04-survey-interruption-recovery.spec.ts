import { expect, test } from '@playwright/test'
import { startSinglePersonaSurvey } from './helpers'

test('closing the observer does not stop a run and reattachment loses no durable events', async ({ page }) => {
  await startSinglePersonaSurvey(page, {
    label: 'E2E 再接続復旧',
    theme: '投資一任サービスの初回相談体験',
  })

  await expect(page.getByTestId('survey-runner-screen')).toBeVisible()
  await expect(page.getByTestId('survey-connection-state')).toHaveText('接続中', { timeout: 30_000 })
  const runId = await page.evaluate(() => sessionStorage.getItem('active-survey-run-id'))
  expect(runId).toBeTruthy()

  // Reloading closes the original EventSource only. The process-owned run must
  // continue and the application must hydrate snapshots and attach again.
  await page.reload()
  await expect(page.getByTestId('survey-runner-screen')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('survey-connection-state')).toHaveText('接続中', { timeout: 30_000 })
  await expect(page.getByTestId('survey-answer-block').first()).toBeVisible({ timeout: 180_000 })

  const deadline = Date.now() + 180_000
  let detail: { status: string; answers: unknown[]; questions: unknown[] } | undefined
  while (Date.now() < deadline) {
    const response = await page.request.get(`/api/history/${runId}`)
    expect(response.ok()).toBeTruthy()
    detail = await response.json()
    if (detail?.status !== 'running') break
    await page.waitForTimeout(500)
  }
  expect(detail?.status).toBe('completed')
  expect(detail?.answers.length).toBe(detail!.questions.length)

  const replay = await page.request.get(`/api/survey/stream/${runId}`)
  expect(replay.ok()).toBeTruthy()
  const ids = (await replay.text()).split('\n')
    .filter((line) => line.startsWith('id: '))
    .map((line) => Number(line.slice(4)))
  expect(ids).toEqual(Array.from({ length: ids.length }, (_, index) => index + 1))
})
