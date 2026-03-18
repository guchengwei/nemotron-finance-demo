import { expect, test } from '@playwright/test'
import { containsJapanese, gotoHome, textOf } from './helpers'

test('AI question generation changes with the theme when using the real LLM', async ({ page }) => {
  await gotoHome(page)
  await page.getByTestId('custom-survey-button').click()
  await expect(page.getByTestId('survey-config-screen')).toBeVisible()

  const themeInput = page.getByTestId('survey-theme-input')
  const generateButton = page.getByTestId('generate-questions-button')

  await themeInput.fill('住宅ローン相談AIの導入に対する顧客反応')
  await generateButton.click()
  await expect(page.getByTestId('survey-question-0')).toBeVisible()

  const firstBatch = await Promise.all(
    Array.from({ length: 3 }, (_, index) => textOf(page.getByTestId(`survey-question-${index}`))),
  )

  firstBatch.forEach((question) => expect(containsJapanese(question)).toBeTruthy())

  await themeInput.fill('高校生向けキャッシュレス教育アプリの受容性')
  await generateButton.click()
  await expect(page.getByTestId('survey-question-0')).toBeVisible()

  const secondBatch = await Promise.all(
    Array.from({ length: 3 }, (_, index) => textOf(page.getByTestId(`survey-question-${index}`))),
  )

  secondBatch.forEach((question) => expect(containsJapanese(question)).toBeTruthy())
  expect(secondBatch.join('\n')).not.toEqual(firstBatch.join('\n'))
})
