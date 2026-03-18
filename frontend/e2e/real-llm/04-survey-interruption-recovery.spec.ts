import { expect, test } from '@playwright/test'
import { startSinglePersonaSurvey, textOf } from './helpers'

test('an interrupted survey stays recoverable and reopens in step 3 after refresh', async ({ page }) => {
  await startSinglePersonaSurvey(page, {
    label: 'E2E 中断復旧',
    theme: '投資一任サービスの初回相談体験',
    scenario: 'survey_fail_mid_run',
  })

  await expect(page.getByTestId('survey-interruption-banner')).toBeVisible({ timeout: 180_000 })
  await expect(page.getByTestId('survey-runner-screen')).toBeVisible()

  const answerBlocks = page.getByTestId('survey-answer-block')
  await expect(answerBlocks.first()).toBeVisible()
  const answerText = await textOf(answerBlocks.first())
  expect(answerText).not.toContain('<think>')
  expect(answerText).not.toContain('</think>')

  await page.reload()
  await expect(page.getByTestId('quick-demo-button')).toBeVisible()

  const interruptedRun = page.getByRole('button', { name: /E2E 中断復旧/ })
  await interruptedRun.click()

  await expect(page.getByTestId('survey-runner-screen')).toBeVisible()
  await expect(page.getByTestId('survey-interruption-banner')).toBeVisible()
  await expect(answerBlocks.first()).toBeVisible()

  const statusBadge = interruptedRun.getByTestId(/history-run-status-/)
  await expect(statusBadge).not.toHaveText('実行中')
})
