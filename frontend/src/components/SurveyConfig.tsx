import { useState } from 'react'
import { api } from '../api'
import { useStore, SURVEY_PRESETS } from '../store'
import { useSurvey } from '../hooks/useSurvey'


const DEFAULT_THEME = 'AIを活用した資産運用アドバイザリーサービスの導入に対する金融機関顧客の反応'

export default function SurveyConfig() {
  const {
    selectedPersonas, surveyTheme, setSurveyTheme,
    questions, setQuestions, surveyLabel, setSurveyLabel,
    setStep, enableThinking, setEnableThinking, currentHistoryRun,
  } = useStore()
  const { startSurvey } = useSurvey()

  const llmStatus = useStore(s => s.llmStatus)
  const [generatingQuestions, setGeneratingQuestions] = useState(false)
  const [genError, setGenError] = useState<string | null>(null)
  const [editingIdx, setEditingIdx] = useState<number | null>(null)
  const [selectedPreset, setSelectedPreset] = useState<string>('')

  const { currentRunId, personaStates } = useStore()

  const estimatedMinutes = Math.ceil(selectedPersonas.length * questions.length * 3 / 60)
  const isCompletedReview = currentHistoryRun?.status === 'completed'
  const isActiveRun = !!(currentRunId || Object.keys(personaStates).length > 0)
  const isReadOnly = isCompletedReview || isActiveRun

  const generateQuestions = async () => {
    if (!surveyTheme) return
    setGenError(null)
    setGeneratingQuestions(true)
    try {
      const response = await api.generateQuestions(surveyTheme)
      setQuestions(response.questions)
    } catch {
      setGenError('質問の生成に失敗しました。LLMサーバーの接続を確認してください。')
    } finally {
      setGeneratingQuestions(false)
    }
  }

  const updateQuestion = (idx: number, value: string) => {
    const updated = [...questions]
    updated[idx] = value
    setQuestions(updated)
  }

  const removeQuestion = (idx: number) => {
    setQuestions(questions.filter((_, i) => i !== idx))
  }

  const addQuestion = () => {
    setQuestions([...questions, ''])
    setEditingIdx(questions.length)
  }

  const handlePresetChange = (presetId: string) => {
    setSelectedPreset(presetId)
    if (!presetId) return
    const preset = SURVEY_PRESETS.find(p => p.id === presetId)
    if (preset) {
      setSurveyTheme(preset.theme)
      setQuestions(preset.questions)
    }
  }

  const handleStart = () => {
    setStep(3)
    startSurvey()
  }

  if (isReadOnly) {
    return (
      <div data-testid="survey-config-screen" className="max-w-2xl space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold tracking-[-0.03em] text-fin-ink">調査設定</h2>
          <span className="rounded-full bg-fin-accentSoft px-3 py-1 text-xs font-medium text-fin-accent">
            完了済み（閲覧のみ）
          </span>
        </div>

        <div>
          <label className="mb-2 block text-xs font-semibold text-fin-muted">調査テーマ</label>
          <div className="w-full rounded-[1.5rem] border border-fin-border bg-fin-panel px-4 py-3 text-sm text-fin-ink">
            {surveyTheme || '—'}
          </div>
        </div>

        {surveyLabel && (
          <div>
            <label className="mb-2 block text-xs font-semibold text-fin-muted">ラベル</label>
            <div className="w-full rounded-full border border-fin-border bg-fin-panel px-4 py-3 text-sm text-fin-ink">
              {surveyLabel}
            </div>
          </div>
        )}

        <div className="flex items-center justify-between rounded-[1.5rem] border border-fin-border bg-fin-surface px-4 py-3 shadow-card">
          <div>
            <div className="text-sm font-medium text-fin-ink">モデル思考モード</div>
            <div className="text-xs text-fin-muted">実行時の設定</div>
          </div>
          <div className={`rounded-full px-3 py-1 text-xs font-medium ${enableThinking ? 'bg-fin-accent text-fin-surface' : 'bg-fin-border text-fin-muted'}`}>
            {enableThinking ? 'ON' : 'OFF'}
          </div>
        </div>

        <div>
          <label className="mb-2 block text-xs font-semibold text-fin-muted">質問項目</label>
          <div className="space-y-2">
            {questions.map((q, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="mt-2.5 w-4 flex-shrink-0 text-xs text-fin-muted">{i + 1}</span>
                <div className="flex-1 rounded-2xl border border-fin-border bg-fin-panel px-3 py-2 text-sm text-fin-ink">
                  {q}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div data-testid="survey-config-screen" className="max-w-2xl space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold tracking-[-0.03em] text-fin-ink">調査設定</h2>
        <div className="text-sm text-fin-muted">
          {selectedPersonas.length}名選択済み
        </div>
      </div>

      <div>
        <label className="mb-2 block text-xs font-semibold text-fin-muted">プリセット</label>
        <select
          value={selectedPreset}
          onChange={(e) => handlePresetChange(e.target.value)}
          className="w-full rounded-full border border-fin-border bg-fin-surface px-4 py-3 text-sm text-fin-ink shadow-card transition-colors focus:border-fin-accent focus:outline-none"
        >
          <option value="">カスタム</option>
          {SURVEY_PRESETS.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="mb-2 block text-xs font-semibold text-fin-muted">
          調査テーマ <span className="text-red-500">*</span>
        </label>
        <textarea
          data-testid="survey-theme-input"
          value={surveyTheme}
          onChange={(e) => setSurveyTheme(e.target.value)}
          placeholder={DEFAULT_THEME}
          rows={3}
          className="w-full resize-none rounded-[1.5rem] border border-fin-border bg-fin-surface px-4 py-3 text-sm text-fin-ink shadow-card transition-colors placeholder:text-fin-muted focus:border-fin-accent focus:outline-none"
        />
      </div>

      <div>
        <label className="mb-2 block text-xs font-semibold text-fin-muted">ラベル（任意）</label>
        <input
          data-testid="survey-label-input"
          type="text"
          value={surveyLabel}
          onChange={(e) => setSurveyLabel(e.target.value)}
          placeholder="例: 投信オンライン_40代男性_東京"
          className="w-full rounded-full border border-fin-border bg-fin-surface px-4 py-3 text-sm text-fin-ink shadow-card transition-colors placeholder:text-fin-muted focus:border-fin-accent focus:outline-none"
        />
      </div>

      <div className="flex items-center justify-between rounded-[1.5rem] border border-fin-border bg-fin-surface px-4 py-3 shadow-card">
        <div>
          <div className="text-sm font-medium text-fin-ink">モデル思考モード</div>
          <div className="text-xs text-fin-muted">ONにすると推論が深くなりますが、回答に時間がかかります</div>
        </div>
        <button
          onClick={() => setEnableThinking(!enableThinking)}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${enableThinking ? 'bg-fin-accent' : 'bg-fin-border'}`}
        >
          <span className={`inline-block h-4 w-4 transform rounded-full bg-fin-surface shadow transition-transform ${enableThinking ? 'translate-x-6' : 'translate-x-1'}`} />
        </button>
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs font-semibold text-fin-muted">質問項目</label>
          <button
            data-testid="generate-questions-button"
            onClick={generateQuestions}
            disabled={!surveyTheme || generatingQuestions}
            className="text-xs font-medium text-fin-accent transition-colors hover:text-fin-accentStrong disabled:opacity-50"
          >
            {generatingQuestions ? '生成中...' : 'AIに質問を生成させる'}
          </button>
        </div>
        {llmStatus && !llmStatus.llm_reachable && !llmStatus.mock_llm && (
          <p className="mb-2 text-xs text-fin-warning">
            LLMサーバーに接続できません。モックモードでの実行を検討してください。
          </p>
        )}
        {genError && (
          <p className="mt-2 text-xs text-fin-danger">{genError}</p>
        )}
        <div className="space-y-2">
          {questions.map((q, i) => (
            <div key={i} className="flex items-start gap-2">
              <span className="mt-2.5 w-4 flex-shrink-0 text-xs text-fin-muted">{i + 1}</span>
              {editingIdx === i ? (
                <textarea
                  data-testid={`survey-question-${i}`}
                  autoFocus
                  value={q}
                  onChange={(e) => updateQuestion(i, e.target.value)}
                  onBlur={() => setEditingIdx(null)}
                  rows={2}
                  className="flex-1 resize-none rounded-2xl border border-fin-accent bg-fin-surface px-3 py-2 text-sm text-fin-ink shadow-card focus:outline-none"
                />
              ) : (
                <button
                  data-testid={`survey-question-${i}`}
                  onClick={() => setEditingIdx(i)}
                  className="flex-1 rounded-2xl border border-fin-border bg-fin-surface px-3 py-2 text-left text-sm text-fin-ink shadow-card transition-all duration-200 hover:border-fin-accent/40"
                >
                  {q || <span className="text-fin-muted">（クリックして編集）</span>}
                </button>
              )}
              <button
                data-testid="survey-question-remove"
                onClick={() => removeQuestion(i)}
                className="mt-1.5 text-lg leading-none text-fin-muted transition-colors hover:text-fin-danger"
              >
                ×
              </button>
            </div>
          ))}
          <button
            onClick={addQuestion}
            className="mt-1 text-xs font-medium text-fin-accent transition-colors hover:text-fin-accentStrong"
          >
            ＋ 質問を追加
          </button>
        </div>
      </div>

      <div className="rounded-[1.5rem] border border-fin-border bg-fin-panel px-4 py-3 text-sm text-fin-muted">
        推定所要時間: 約 <span className="font-bold text-fin-ink">{estimatedMinutes}分</span>
        <span className="ml-2 text-fin-muted/80">
          ({selectedPersonas.length}名 × {questions.length}問 × ~3秒/回答)
        </span>
      </div>

      <button
        onClick={handleStart}
        disabled={!surveyTheme || questions.length === 0 || selectedPersonas.length === 0}
        className="w-full rounded-full bg-fin-accent px-6 py-3 text-base font-semibold text-fin-surface transition-all duration-200 hover:-translate-y-0.5 hover:bg-fin-accentStrong disabled:cursor-not-allowed disabled:opacity-50"
      >
        調査を開始する →
      </button>
    </div>
  )
}
