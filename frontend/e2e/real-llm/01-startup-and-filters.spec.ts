import { expect, test } from '@playwright/test'
import { gotoHome } from './helpers'

test('app boots against the real backend and filter counts keep the last response', async ({ page }) => {
  let requestIndex = 0

  await page.route('**/api/personas/count**', async (route) => {
    requestIndex += 1
    if (requestIndex === 1) {
      await new Promise((resolve) => setTimeout(resolve, 700))
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ total_matching: 111 }),
      })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ total_matching: 222 }),
    })
  })

  await gotoHome(page)

  const matchCount = page.getByTestId('match-count')
  await expect(matchCount).not.toHaveText('—')

  const sexSelect = page.locator('select').first()
  await sexSelect.selectOption('男')
  await page.waitForTimeout(350)
  await sexSelect.selectOption('女')

  await expect(matchCount).not.toHaveText('—')
  await expect(matchCount).toContainText('222')
})
