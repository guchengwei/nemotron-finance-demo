import { expect, type Locator, type Page } from '@playwright/test'

export const SEEDED_RUN_LABEL = 'E2E 深掘りシード'

export function containsJapanese(text: string) {
  return /[\u3040-\u30ff\u3400-\u9fff]/.test(text)
}

export async function gotoHome(page: Page) {
  await page.goto('/')
  await expect(page.getByTestId('quick-demo-button')).toBeVisible()
}

export async function addScenarioHeader(page: Page, urlPattern: string, scenario: string) {
  await page.route(urlPattern, async (route) => {
    await route.continue({
      headers: {
        ...route.request().headers(),
        'X-E2E-Scenario': scenario,
      },
    })
  })
}

export async function rewriteQuickDemoSampleCount(page: Page, count: number) {
  await page.route('**/api/personas/sample**', async (route) => {
    const requestUrl = new URL(route.request().url())
    requestUrl.searchParams.set('count', String(count))
    await route.continue({ url: requestUrl.toString() })
  })
}

export async function openSurveyConfigWithOnePersona(page: Page) {
  await gotoHome(page)
  await page.getByPlaceholder('カスタム').fill('1')
  await page.getByRole('button', { name: 'ペルソナを抽出 (1名)' }).click()
  await expect(page.getByTestId('persona-sampled-section')).toBeVisible()
  await page.getByRole('button', { name: '次へ: 調査設定 →' }).click()
  await expect(page.getByTestId('survey-config-screen')).toBeVisible()
}

export async function reduceQuestionsToOne(page: Page) {
  const removeButtons = page.getByTestId('survey-question-remove')
  while (await removeButtons.count() > 1) {
    await removeButtons.last().click()
  }
}

export async function startSinglePersonaSurvey(
  page: Page,
  {
    label,
    theme,
    scenario,
  }: { label: string; theme: string; scenario?: string },
) {
  if (scenario) {
    await addScenarioHeader(page, '**/api/survey/run', scenario)
  }

  await openSurveyConfigWithOnePersona(page)
  await reduceQuestionsToOne(page)
  await page.getByTestId('survey-theme-input').fill(theme)
  await page.getByTestId('survey-label-input').fill(label)
  await page.getByRole('button', { name: '調査を開始する →' }).click()
  await expect(page.getByTestId('survey-runner-screen')).toBeVisible()
}

export async function textOf(locator: Locator) {
  return (await locator.textContent())?.trim() || ''
}
