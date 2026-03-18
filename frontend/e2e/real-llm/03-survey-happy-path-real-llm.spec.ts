import { expect, test } from '@playwright/test'
import { containsJapanese, startSinglePersonaSurvey, textOf } from './helpers'

test('single-person survey completes with separated answer rendering and a report', async ({ page }) => {
  await startSinglePersonaSurvey(page, {
    label: 'E2E ハッピーパス',
    theme: 'オンライン投資相談サービスの初期受容性',
  })

  await expect(page.getByTestId('survey-active-answer-block')).toBeVisible()
  const activeAnswer = await textOf(page.getByTestId('survey-active-answer-block'))
  if (activeAnswer) {
    expect(activeAnswer).not.toContain('<think>')
    expect(activeAnswer).not.toContain('</think>')
  }

  const thinkingBlocks = page.getByTestId('survey-thinking-block')
  if (await thinkingBlocks.count()) {
    await expect(thinkingBlocks.first()).not.toHaveAttribute('open', '')
  }

  await expect(page.getByTestId('report-dashboard-screen')).toBeVisible({ timeout: 240_000 })

  const answerBlocks = page.getByTestId('survey-answer-block')
  if (await answerBlocks.count()) {
    const answerText = await textOf(answerBlocks.first())
    expect(answerText).not.toContain('<think>')
    expect(answerText).not.toContain('</think>')
    expect(containsJapanese(answerText)).toBeTruthy()
  }
})
