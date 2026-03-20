import { expect, test } from '@playwright/test'
import { filtersFixture, samplePersona } from './fixtures/personas'

test('new survey resets app from progressed state', async ({ page }) => {
  await page.route('**/ready', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ready' }),
    })
  })

  await page.route('**/health', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', mock_llm: true, llm_reachable: true }),
    })
  })

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
  await expect(page.getByTestId('quick-demo-button')).toBeVisible()
  await page.getByRole('button', { name: 'ペルソナを抽出 (8名)' }).click()
  await expect(page.getByRole('heading', { name: 'ペルソナ選択' })).toBeVisible()
  await expect(page.getByText('設定済み（閲覧のみ）')).toBeVisible()
  await expect(page.getByText('1名 抽出済み')).toBeVisible()

  await page.getByTestId('new-survey-button').click()

  await expect(page.getByTestId('quick-demo-button')).toBeVisible()
  await expect(page.getByText('設定済み（閲覧のみ）')).toHaveCount(0)
})
