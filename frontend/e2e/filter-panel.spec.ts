import { expect, test } from '@playwright/test'
import { filtersFixture } from './fixtures/personas'

test.beforeEach(async ({ page }) => {
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
})

test('filter hit count updates for latest dropdown selection', async ({ page }) => {
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
    const url = new URL(route.request().url())
    const sex = url.searchParams.get('sex')

    if (sex === '男') {
      await new Promise((resolve) => setTimeout(resolve, 250))
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ total_matching: 3 }),
      })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ total_matching: 7 }),
    })
  })

  await page.goto('/')
  const sexSelect = page.locator('select').first()
  await sexSelect.selectOption('男')
  await sexSelect.selectOption('女')

  await expect(page.getByTestId('match-count')).toHaveText('7')
})

test('loading state clears once filters are ready', async ({ page }) => {
  let releaseFilters: (() => void) | undefined
  const filtersReleased = new Promise<void>((resolve) => {
    releaseFilters = resolve
  })

  await page.route('**/api/personas/filters', async (route) => {
    await filtersReleased
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

  await page.goto('/')
  await expect(page.getByTestId('filters-loading')).toBeVisible()

  releaseFilters?.()

  await expect(page.getByTestId('filters-loading')).toBeHidden()
})
