import { expect, test } from '@playwright/test'
import { gotoHome, rewriteQuickDemoSampleCount } from './helpers'

test('quick demo creates one run entry for one click', async ({ page }) => {
  await rewriteQuickDemoSampleCount(page, 1)
  await gotoHome(page)

  const quickDemoButton = page.getByTestId('quick-demo-button')
  await quickDemoButton.click()
  await expect(quickDemoButton).toBeDisabled()
  await expect(page.getByTestId('survey-runner-screen')).toBeVisible()

  await page.reload()
  await expect(page.getByTestId('quick-demo-button')).toBeVisible()

  const quickDemoRuns = page.getByRole('button', { name: /クイックデモ/ })
  await expect(quickDemoRuns).toHaveCount(1)
})
