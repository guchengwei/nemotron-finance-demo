#!/usr/bin/env node
/**
 * Standalone screenshot capture script.
 *
 * Captures demo screenshots of the app in mock mode (no real backend required).
 * All API calls are intercepted in-process; only the Vite preview server needs
 * to be running on port 3000.
 *
 * Usage (from repo root):
 *   node scripts/capture-screenshots.mjs
 *
 * Or via npm (from frontend/):
 *   npm run screenshots
 *
 * Environment variable overrides (for non-standard setups):
 *   PLAYWRIGHT_LIB          Path to playwright's index.mjs
 *                           Default: <repo>/frontend/node_modules/playwright/index.mjs
 *   PLAYWRIGHT_EXECUTABLE   Path to the Chromium/headless-shell binary
 *                           Default: auto-discovered by Playwright
 */

import { connect } from 'net'
import { spawn } from 'child_process'
import { mkdirSync, existsSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'

// ── Paths ──────────────────────────────────────────────────────────────────

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const FRONTEND_DIR = join(REPO_ROOT, 'frontend')
const SCREENSHOTS_DIR = join(REPO_ROOT, 'docs', 'screenshots')

// Resolve playwright from local project deps; allow override via env var.
const LOCAL_PW = join(FRONTEND_DIR, 'node_modules', 'playwright', 'index.mjs')
const PLAYWRIGHT_LIB = process.env.PLAYWRIGHT_LIB ?? LOCAL_PW

// Browser executable: use env var override, else let Playwright auto-discover.
// Set PLAYWRIGHT_EXECUTABLE to a specific binary when the project's installed
// browser version doesn't match the available system binary.
const PLAYWRIGHT_EXECUTABLE = process.env.PLAYWRIGHT_EXECUTABLE ?? null

// ── Mock data ──────────────────────────────────────────────────────────────

const RUN_ID = 'demo-screenshots-run-001'

const richFilters = {
  sex: ['男', '女'],
  age_ranges: ['20-29', '30-39', '40-49', '50-59', '60-69'],
  regions: ['関東', '関西', '東海', '九州', '北海道・東北'],
  prefectures: ['東京都', '神奈川県', '大阪府', '愛知県', '福岡県'],
  occupations_top50: ['会社員', 'フリーランス', '自営業', '公務員', '医療・福祉', '教育・研究', '金融・保険'],
  education_levels: ['大学卒', '大学院卒', '短大・専門卒', '高校卒'],
  financial_literacy: ['初心者', '中級者', '上級者'],
  total_count: 4872,
}

const demoPersonas = [
  { uuid: 'p1', name: '田中健一', age: 42, sex: '男', prefecture: '東京都', region: '関東', occupation: '会社員', education_level: '大学卒', marital_status: '既婚', persona: 'ITマネージャーとして活躍する中堅サラリーマン。デジタルツールへの親和性が高く、資産形成に積極的。', professional_persona: 'ITマネージャー', cultural_background: '都市部', skills_and_expertise: 'IT・プロジェクト管理', hobbies_and_interests: '投資・ゴルフ', career_goals_and_ambitions: '早期リタイアを目指した資産形成' },
  { uuid: 'p2', name: '鈴木美咲', age: 31, sex: '女', prefecture: '大阪府', region: '関西', occupation: 'フリーランス', education_level: '大学院卒', marital_status: '未婚', persona: 'UIデザイナーとして独立。収入変動があるため自動資産管理に強い関心を持つ。', professional_persona: 'UIデザイナー', cultural_background: '都市部', skills_and_expertise: 'デザイン・マーケティング', hobbies_and_interests: 'カフェ巡り・読書', career_goals_and_ambitions: '安定した収入基盤の確立' },
  { uuid: 'p3', name: '佐藤誠', age: 55, sex: '男', prefecture: '愛知県', region: '東海', occupation: '自営業', education_level: '大学卒', marital_status: '既婚', persona: '製造業で自営業を営む経営者。アナログ志向が強くデジタル化には慎重なスタンス。', professional_persona: '中小企業経営者', cultural_background: '地方都市', skills_and_expertise: '製造・経営管理', hobbies_and_interests: '釣り・野球観戦', career_goals_and_ambitions: '事業承継と老後の安定' },
  { uuid: 'p4', name: '高橋亮子', age: 28, sex: '女', prefecture: '福岡県', region: '九州', occupation: '会社員', education_level: '大学卒', marital_status: '未婚', persona: 'マーケティング職の若手社員。つみたてNISAを始めたばかりで長期資産形成に積極的。', professional_persona: 'マーケティング担当', cultural_background: '都市部', skills_and_expertise: 'マーケティング・SNS運用', hobbies_and_interests: '旅行・料理', career_goals_and_ambitions: '将来のための長期的な資産形成' },
]

const surveyAnswers = {
  p1: [
    { answer: '複数の口座を一括管理できる点が非常に魅力的です。直感的なUIと資産の可視化機能はITに慣れた自分にとって大きなプラスです。スマートフォンからの即時確認も便利です。', score: 4 },
    { answer: 'セキュリティの堅牢さと既存銀行アプリとの連携がスムーズかどうかが鍵です。個人情報漏洩リスクに対する具体的な対策説明が欲しいです。', score: 3 },
  ],
  p2: [
    { answer: 'フリーランスとして収入が不規則なため、AIが自動で資産を最適化してくれる機能に強く惹かれます。確定申告との連携機能があればさらに価値が上がります。', score: 5 },
    { answer: '月額費用が収入の少ない月に負担になる可能性があります。収入連動型の料金体系や基本無料プランがあれば導入しやすいです。', score: 2 },
  ],
  p3: [
    { answer: '事業と個人の資産を分けながら全体を把握できる点は評価できますが、現在の会計ソフトとの互換性が心配です。紙の通帳に慣れており操作に自信がありません。', score: 2 },
    { answer: '操作が複雑だと使いこなせません。丁寧なチュートリアルと電話サポートがあれば安心できます。データ移行の手間も大きな障壁です。', score: 4 },
  ],
  p4: [
    { answer: 'つみたてNISAの管理から老後の資産形成まで一元管理できる点が非常に魅力的です。AIアドバイス機能で長期的な資産形成をサポートしてくれることに期待しています。', score: 5 },
    { answer: '個人情報の第三者提供ポリシーが気になります。プライバシー保護の仕組みが明確なら安心して利用できます。', score: 2 },
  ],
}

function buildSurveySSE() {
  const questions = [
    'このデジタル資産管理サービスへの関心度と利用意向を教えてください。',
    '導入する際の障壁や懸念点があれば具体的にお聞かせください。',
  ]
  const events = [
    { event: 'run_created', data: { run_id: RUN_ID } },
    { event: 'questions_generated', data: { questions } },
  ]
  for (const p of demoPersonas) {
    events.push({ event: 'persona_start', data: { persona_uuid: p.uuid } })
    for (let qi = 0; qi < questions.length; qi++) {
      events.push({ event: 'persona_answer', data: { persona_uuid: p.uuid, question_index: qi, answer: surveyAnswers[p.uuid][qi].answer, score: surveyAnswers[p.uuid][qi].score } })
    }
    events.push({ event: 'persona_complete', data: { persona_uuid: p.uuid } })
  }
  events.push({ event: 'survey_complete', data: { completed: 4, failed: 0 } })
  return events.map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`).join('')
}

function buildMatrixSSE() {
  const axisConfig = {
    x_axis: { name: '関心度', rubric: '低関心から高関心', label_low: '低関心', label_high: '高関心' },
    y_axis: { name: '導入障壁', rubric: '低障壁から高障壁', label_low: '低障壁', label_high: '高障壁' },
    quadrants: [
      { position: 'top-left', label: '様子見層', subtitle: '低関心・高障壁' },
      { position: 'top-right', label: '潜在採用層', subtitle: '高関心・高障壁' },
      { position: 'bottom-left', label: '慎重観察層', subtitle: '低関心・低障壁' },
      { position: 'bottom-right', label: '即時採用層', subtitle: '高関心・低障壁' },
    ],
  }
  const scoredPersonas = [
    { persona_id: 'p1', name: '田中健一', x_score: 4, y_score: 3, keywords: [{ text: '資産一元管理', polarity: 'strength' }, { text: 'セキュリティ懸念', polarity: 'weakness' }], quadrant_label: '潜在採用層', industry: '会社員', age: 42 },
    { persona_id: 'p2', name: '鈴木美咲', x_score: 5, y_score: 2, keywords: [{ text: 'AI機能', polarity: 'strength' }, { text: 'コスト懸念', polarity: 'weakness' }], quadrant_label: '即時採用層', industry: 'フリーランス', age: 31 },
    { persona_id: 'p3', name: '佐藤誠', x_score: 2, y_score: 4, keywords: [{ text: '操作複雑性', polarity: 'weakness' }, { text: 'サポート要求', polarity: 'weakness' }], quadrant_label: '様子見層', industry: '自営業', age: 55 },
    { persona_id: 'p4', name: '高橋亮子', x_score: 5, y_score: 1, keywords: [{ text: 'つみたて投資', polarity: 'strength' }, { text: 'AI提案', polarity: 'strength' }], quadrant_label: '即時採用層', industry: '会社員', age: 28 },
  ]
  const keywords = {
    strengths: [
      { text: 'AI機能', polarity: 'strength', count: 2, elaboration: 'AIによる自動最適化・アドバイス機能への期待が高い', persona_names: ['鈴木美咲', '高橋亮子'] },
      { text: '資産一元管理', polarity: 'strength', count: 2, elaboration: '複数口座の一括管理による利便性が評価されている', persona_names: ['田中健一', '高橋亮子'] },
      { text: 'つみたて投資', polarity: 'strength', count: 1, elaboration: '長期資産形成との相性が良いと判断されている', persona_names: ['高橋亮子'] },
    ],
    weaknesses: [
      { text: 'セキュリティ懸念', polarity: 'weakness', count: 2, elaboration: '個人情報保護とデータセキュリティへの不安', persona_names: ['田中健一', '高橋亮子'] },
      { text: '操作複雑性', polarity: 'weakness', count: 1, elaboration: 'シニア層やアナログ志向ユーザーにとっての操作障壁', persona_names: ['佐藤誠'] },
      { text: 'コスト懸念', polarity: 'weakness', count: 1, elaboration: '収入変動時の月額費用負担', persona_names: ['鈴木美咲'] },
    ],
  }
  const recommendations = [
    { title: '即時採用層への積極展開', highlight_tag: '最優先', body: '高関心・低障壁の鈴木・高橋層を中心に、AI機能とつみたて投資管理の訴求でオンボーディングを強化する。' },
    { title: 'セキュリティの可視化によるエンゲージメント向上', highlight_tag: '重要', body: '田中層の潜在採用を促進するため、セキュリティ対策の具体的な説明とデータ保護ポリシーの透明性を高める。' },
    { title: 'シニア向けUX改善とサポート整備', highlight_tag: '中期課題', body: '佐藤層の取り込みには簡易操作モードと充実した電話サポート体制の整備が必要。' },
  ]
  const scoreTable = scoredPersonas.map((p) => ({ persona_id: p.persona_id, name: p.name, x_score: p.x_score, y_score: p.y_score, industry: p.industry, age: p.age, quadrant_label: p.quadrant_label }))
  const events = [
    { event: 'axis_ready', data: axisConfig },
    ...scoredPersonas.map((p) => ({ event: 'persona_scored', data: p })),
    { event: 'keywords_ready', data: keywords },
    { event: 'recommendations_ready', data: recommendations },
    { event: 'score_table_ready', data: scoreTable },
    { event: 'report_complete', data: {} },
  ]
  return events.map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`).join('')
}

// ── Server helpers ─────────────────────────────────────────────────────────

/** Returns true when a TCP server is accepting connections on the port. */
function isPortListening(port) {
  return new Promise((resolve) => {
    const sock = connect({ port, host: '127.0.0.1' })
    sock.once('connect', () => { sock.destroy(); resolve(true) })
    sock.once('error', () => resolve(false))
  })
}

async function waitForPort(port, timeoutMs = 30000) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    if (await isPortListening(port)) return
    await new Promise((r) => setTimeout(r, 300))
  }
  throw new Error(`Timed out waiting for port ${port}`)
}

// ── Main ───────────────────────────────────────────────────────────────────

async function main() {
  mkdirSync(SCREENSHOTS_DIR, { recursive: true })

  // Start Vite preview server if not already running
  const alreadyRunning = await isPortListening(3000)
  let serverProc = null
  if (!alreadyRunning) {
    console.log('Starting Vite preview server…')
    serverProc = spawn('npm run preview -- --host 127.0.0.1 --port 3000', {
      cwd: FRONTEND_DIR,
      shell: true,
      stdio: 'pipe',
    })
    serverProc.stderr.on('data', (d) => process.stderr.write(d))
    await waitForPort(3000)
    console.log('Vite preview server ready.')
  } else {
    console.log('Using existing server on :3000')
  }

  if (!existsSync(PLAYWRIGHT_LIB)) {
    throw new Error(
      `Playwright library not found at ${PLAYWRIGHT_LIB}.\n` +
      'Run "npm install" inside frontend/ or set PLAYWRIGHT_LIB to the correct path.'
    )
  }

  const { chromium } = await import(PLAYWRIGHT_LIB)

  const launchOptions = {
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  }
  if (PLAYWRIGHT_EXECUTABLE) {
    launchOptions.executablePath = PLAYWRIGHT_EXECUTABLE
  }

  const browser = await chromium.launch(launchOptions)

  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } })
  const page = await context.newPage()

  // ── Register all API mocks ──────────────────────────────────────────────

  await context.route('**/ready', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ready' }) }))
  await context.route('**/health', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', mock_llm: true, llm_reachable: true }) }))
  await context.route('**/api/personas/filters', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(richFilters) }))
  await context.route('**/api/history', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ runs: [] }) }))
  await context.route('**/api/personas/count**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ total_matching: 4872 }) }))
  await context.route('**/api/personas/sample**', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ total_matching: 4, sampled: demoPersonas }) }))
  await context.route('**/api/survey/run', (r) => r.fulfill({ status: 200, contentType: 'text/event-stream', body: buildSurveySSE() }))
  await context.route('**/api/report/generate', (r) =>
    r.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ run_id: RUN_ID, overall_score: 4.0, group_tendency: '全体的に高い関心を持ちながらも、セキュリティと操作性に関する懸念が障壁となっています。若年層とデジタルネイティブ層は即時採用ポテンシャルが高く、シニア層は丁寧な導線設計が必要です。', conclusion: 'デジタル資産管理サービスは特に20〜30代のデジタルネイティブ層に強い訴求力があります。セキュリティの透明化とAI機能の充実を軸に展開することで、採用率の最大化が期待できます。', top_picks: [] }),
    })
  )
  await context.route('**/api/report/matrix', (r) => r.fulfill({ status: 200, contentType: 'text/event-stream', body: buildMatrixSSE() }))

  const shot = async (name) => {
    const dest = join(SCREENSHOTS_DIR, name)
    await page.screenshot({ path: dest })
    console.log(`  ✓ ${name}`)
  }

  // ── 01: Filter Panel ──────────────────────────────────────────────────

  console.log('\nCapturing screenshots…')
  await page.goto('http://127.0.0.1:3000/')
  await page.waitForSelector('select', { timeout: 20000 })
  await new Promise((r) => setTimeout(r, 500))
  await shot('01-filter-panel.png')

  // ── 02: Survey Config ─────────────────────────────────────────────────

  await page.fill('[placeholder="カスタム"]', '4')
  await page.click('button:has-text("ペルソナを抽出")')
  await page.waitForSelector('h2, h1, [role="heading"]', { timeout: 15000 })
  // Click step 2 button
  const step2 = page.locator('button', { hasText: '調査設定' })
  await step2.waitFor({ timeout: 10000 })
  await step2.click()
  await page.waitForSelector('[data-testid="survey-config-screen"]', { timeout: 10000 })
  await page.fill('[data-testid="survey-theme-input"]', 'デジタル資産管理サービスの顧客適合性調査')
  await new Promise((r) => setTimeout(r, 400))
  await shot('02-survey-config.png')

  // ── 03: Survey Runner ─────────────────────────────────────────────────

  await page.click('button:has-text("調査を開始する")')
  await page.waitForSelector('[data-testid="survey-runner-screen"]', { timeout: 15000 })
  await page.waitForSelector('button:has-text("レポートを見る")', { timeout: 30000 })
  await new Promise((r) => setTimeout(r, 400))
  await shot('03-survey-runner.png')

  // ── 04: Matrix Report ─────────────────────────────────────────────────

  await page.click('button:has-text("レポートを見る")')
  await page.waitForSelector('[data-testid="report-dashboard-screen"]', { timeout: 15000 })
  await page.waitForSelector('.rounded-full.border-2', { timeout: 30000 })
  await new Promise((r) => setTimeout(r, 600))
  await shot('04-report-matrix.png')

  await browser.close()

  if (serverProc) {
    serverProc.kill()
  }

  console.log(`\nScreenshots saved to ${SCREENSHOTS_DIR}\n`)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
