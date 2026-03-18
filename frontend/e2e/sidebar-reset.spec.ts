import { expect, test } from '@playwright/test'
import { filtersFixture, samplePersona } from './fixtures/personas'

test('new survey resets app from progressed state', async ({ page }) => {
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

  await page.route('**/api/personas/count**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ total_matching: 100 }),
    })
  })

  await page.route('**/api/personas/sample**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ total_matching: 1, sampled: [samplePersona] }),
    })
  })

  await page.goto('/')
  await page.getByRole('button', { name: 'ペルソナを抽出 (8名)' }).click()
  await expect(page.getByTestId('persona-sampled-section')).toBeVisible()

  await page.getByTestId('new-survey-button').click()

  await expect(page.getByRole('heading', { name: 'ペルソナ選択' })).toBeVisible()
  await expect(page.getByTestId('persona-sampled-section')).toHaveCount(0)
})
