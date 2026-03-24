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

test('ランダム is the only browser trigger for randomized count behavior', async ({ page }) => {
  let countRequests = 0

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
    countRequests += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ total_matching: 37 }),
    })
  })

  await page.goto('/')

  await expect(page.locator('select').first()).toHaveValue('')
  await expect(page.locator('select').nth(1)).toHaveValue('')
  await expect(page.locator('input[type="number"]').first()).toHaveValue('20')
  await expect(page.locator('input[type="number"]').nth(1)).toHaveValue('80')
  await expect(page.getByPlaceholder('職業を入力...')).toHaveValue('')
  await expect(page.getByTestId('match-count')).toHaveText('100')

  await page.waitForTimeout(300)
  expect(countRequests).toBe(0)

  await page.getByRole('button', { name: 'ランダム' }).click()

  await expect.poll(() => countRequests).toBe(1)
  await expect(page.locator('select').nth(1)).toHaveValue('関東')
  await expect(page.getByTestId('match-count')).toHaveText('37')
})

test('initial filter load stays at the default unfiltered state without autorun', async ({ page }) => {
  let countRequests = 0

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
    countRequests += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ total_matching: 999 }),
    })
  })

  await page.goto('/')

  await expect(page.locator('select').first()).toHaveValue('')
  await expect(page.locator('select').nth(1)).toHaveValue('')
  await expect(page.locator('select').nth(2)).toHaveValue('')
  await expect(page.locator('select').nth(3)).toHaveValue('')
  await expect(page.locator('input[type="number"]').first()).toHaveValue('20')
  await expect(page.locator('input[type="number"]').nth(1)).toHaveValue('80')
  await expect(page.getByTestId('match-count')).toHaveText('100')

  await page.waitForTimeout(350)

  expect(countRequests).toBe(0)
  await expect(page.getByTestId('match-count')).toHaveText('100')
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
