import { expect, test } from '@playwright/test'
import { filtersFixture, samplePersona } from './fixtures/personas'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/personas/filters', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(filtersFixture),
    })
  })

  await page.route('**/api/history', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ runs: [] }),
    })
  })
})

test('custom survey button navigates to config screen', async ({ page }) => {
  await page.goto('/')
  await page.getByTestId('custom-survey-button').click()
  await expect(page.getByTestId('survey-config-screen')).toBeVisible()
})

test('quick demo shows immediate feedback and opens runner', async ({ page }) => {
  let releaseSample: (() => void) | undefined
  const sampleReleased = new Promise<void>((resolve) => {
    releaseSample = resolve
  })

  await page.route('**/api/personas/sample**', async (route) => {
    await sampleReleased
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ total_matching: 1, sampled: [samplePersona] }),
    })
  })

  await page.goto('/')
  await page.getByTestId('quick-demo-button').click()

  await expect(page.getByTestId('quick-demo-button')).toBeDisabled()

  releaseSample?.()
  await expect(page.getByTestId('survey-runner-screen')).toBeVisible()
})
