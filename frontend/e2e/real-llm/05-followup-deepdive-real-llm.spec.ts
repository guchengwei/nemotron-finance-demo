import { expect, test } from '@playwright/test'
import { containsJapanese, SEEDED_RUN_LABEL, gotoHome, textOf } from './helpers'

test('deep-dive follow-up shows expandable profile and sanitized Japanese answers', async ({ page }) => {
  await gotoHome(page)
  await page.getByRole('button', { name: new RegExp(SEEDED_RUN_LABEL) }).click()

  await expect(page.getByTestId('report-dashboard-screen')).toBeVisible()
  // Switch to text report tab (matrix tab is the default) to access top-pick follow-up buttons
  await page.getByRole('button', { name: 'テキストレポート' }).click()
  await page.getByRole('button', { name: 'この人に質問する →' }).click()

  await expect(page.getByTestId('followup-screen')).toBeVisible()

  const profile = page.getByTestId('followup-profile-text')
  await expect(profile).toHaveClass(/max-h-24/)
  await page.getByTestId('followup-profile-toggle').click()
  await expect(profile).not.toHaveClass(/max-h-24/)

  await page.getByTestId('followup-input').fill('このサービスを試す前に、何を確認できると安心ですか？')
  await page.getByRole('button', { name: '送信' }).click()

  await expect(page.getByTestId('followup-input')).toBeEnabled({ timeout: 180_000 })
  const answerBubble = page.getByTestId('followup-answer-bubble').last()
  await expect(answerBubble).toBeVisible({ timeout: 180_000 })
  await expect(answerBubble).not.toHaveText('', { timeout: 180_000 })

  const thinkingBlocks = page.getByTestId('followup-thinking-block')
  if (await thinkingBlocks.count()) {
    await expect(thinkingBlocks.first()).not.toHaveAttribute('open', '')
  }

  const answerText = await textOf(answerBubble)
  expect(answerText).not.toContain('<think>')
  expect(answerText).not.toContain('</think>')
  expect(containsJapanese(answerText)).toBeTruthy()
})
