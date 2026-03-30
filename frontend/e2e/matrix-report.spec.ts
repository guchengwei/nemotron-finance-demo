import { test, expect } from '@playwright/test'
import { filtersFixture, samplePersona } from './fixtures/personas'

const RUN_ID = 'test-run-matrix-001'

function makeSurveySSE(): string {
  const events: Array<{ event: string; data: unknown }> = [
    { event: 'run_created', data: { run_id: RUN_ID } },
    { event: 'questions_generated', data: { questions: ['このサービスへの関心度を教えてください'] } },
    { event: 'persona_start', data: { persona_uuid: samplePersona.uuid } },
    {
      event: 'persona_answer',
      data: {
        persona_uuid: samplePersona.uuid,
        question_index: 0,
        answer: '関心があります。利便性が高く良いと思います。',
        score: 4,
      },
    },
    { event: 'persona_complete', data: { persona_uuid: samplePersona.uuid } },
    { event: 'survey_complete', data: { completed: 1, failed: 0 } },
  ]
  return events
    .map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`)
    .join('')
}

function makeMatrixSSE(): string {
  const axisConfig = {
    x_axis: {
      name: '関心度',
      rubric: '低関心から高関心',
      label_low: '低関心',
      label_high: '高関心',
    },
    y_axis: {
      name: '導入障壁',
      rubric: '低障壁から高障壁',
      label_low: '低障壁',
      label_high: '高障壁',
    },
    quadrants: [
      { position: 'top-left', label: '様子見層', subtitle: '低関心・高障壁' },
      { position: 'top-right', label: '潜在採用層', subtitle: '高関心・高障壁' },
      { position: 'bottom-left', label: '慎重観察層', subtitle: '低関心・低障壁' },
      { position: 'bottom-right', label: '即時採用層', subtitle: '高関心・低障壁' },
    ],
  }
  const scoredPersona = {
    persona_id: samplePersona.uuid,
    name: samplePersona.name,
    x_score: 4,
    y_score: 2,
    keywords: [{ text: '利便性', polarity: 'strength' }],
    quadrant_label: '即時採用層',
    industry: '会社員',
    age: samplePersona.age,
  }
  const keywords = {
    strengths: [{ text: '利便性', polarity: 'strength', count: 1, elaboration: '高い利便性', persona_names: [samplePersona.name] }],
    weaknesses: [],
  }
  const recommendations = [
    { title: '即時採用層への積極展開', highlight_tag: '推奨', body: '高関心・低障壁層への重点施策を検討' },
  ]
  const scoreTable = [
    {
      persona_id: samplePersona.uuid,
      name: samplePersona.name,
      x_score: 4,
      y_score: 2,
      industry: '会社員',
      age: samplePersona.age,
      quadrant_label: '即時採用層',
    },
  ]

  const events: Array<{ event: string; data: unknown }> = [
    { event: 'axis_ready', data: axisConfig },
    { event: 'persona_scored', data: scoredPersona },
    { event: 'keywords_ready', data: keywords },
    { event: 'recommendations_ready', data: recommendations },
    { event: 'score_table_ready', data: scoreTable },
    { event: 'report_complete', data: {} },
  ]
  return events
    .map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`)
    .join('')
}

test('matrix report renders after survey completes', async ({ page }) => {
  // Mock infrastructure endpoints
  await page.route('**/ready', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ready' }) })
  )
  await page.route('**/health', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', mock_llm: true, llm_reachable: true }),
    })
  )
  await page.route('**/api/personas/filters', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(filtersFixture) })
  )
  await page.route('**/api/history', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ runs: [] }) })
  )
  await page.route('**/api/personas/count**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ total_matching: 1 }) })
  )
  await page.route('**/api/personas/sample**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ total_matching: 1, sampled: [samplePersona] }),
    })
  )

  // Mock survey SSE
  await page.route('**/api/survey/run', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: makeSurveySSE(),
    })
  )

  // Mock report generation
  await page.route('**/api/report/generate', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        run_id: RUN_ID,
        overall_score: 4.0,
        group_tendency: 'テスト傾向分析',
        conclusion: 'テスト結論',
        top_picks: [],
      }),
    })
  )

  // Mock matrix report SSE
  await page.route('**/api/report/matrix', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: makeMatrixSSE(),
    })
  )

  await page.goto('/')

  // Step 1: Extract 1 persona and go to survey config
  await page.getByPlaceholder('カスタム').fill('1')
  await page.getByRole('button', { name: 'ペルソナを抽出 (1名)' }).click()
  await expect(page.getByRole('heading', { name: 'ペルソナ選択' })).toBeVisible()
  await page.getByRole('button', { name: /2 調査設定/ }).click()

  // Step 2: Fill theme and start the survey
  await expect(page.getByTestId('survey-config-screen')).toBeVisible()
  await page.getByTestId('survey-theme-input').fill('テスト調査テーマ')
  await page.getByRole('button', { name: '調査を開始する →' }).click()

  // Step 3: Wait for survey to complete and navigate to report
  await expect(page.getByTestId('survey-runner-screen')).toBeVisible()
  await expect(page.getByRole('button', { name: 'レポートを見る →' })).toBeVisible({ timeout: 30000 })
  await page.getByRole('button', { name: 'レポートを見る →' }).click()

  // Step 4: Verify report dashboard with matrix tab (default)
  await expect(page.getByTestId('report-dashboard-screen')).toBeVisible({ timeout: 10000 })
  await expect(page.getByRole('button', { name: 'マトリクス分析' })).toBeVisible()

  // Wait for at least one persona dot to appear
  await expect(page.locator('.rounded-full.border-2').first()).toBeVisible({ timeout: 30000 })

  // Verify quadrant labels appear in the matrix grid
  await expect(page.locator('div').filter({ hasText: /^様子見層$/ }).first()).toBeVisible()
  await expect(page.locator('div').filter({ hasText: /^即時採用層$/ }).first()).toBeVisible()
})
