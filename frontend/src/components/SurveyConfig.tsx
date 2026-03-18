import { useState } from 'react'
import { useStore } from '../store'
import { useSurvey } from '../hooks/useSurvey'


const DEFAULT_THEME = 'AIを活用した資産運用アドバイザリーサービスの導入に対する金融機関顧客の反応'

export default function SurveyConfig() {
  const {
    selectedPersonas, surveyTheme, setSurveyTheme,
    questions, setQuestions, surveyLabel, setSurveyLabel,
    setStep,
  } = useStore()
  const { startSurvey } = useSurvey()

  const llmStatus = useStore(s => s.llmStatus)
  const [generatingQuestions, setGeneratingQuestions] = useState(false)
  const [genError, setGenError] = useState<string | null>(null)
  const [editingIdx, setEditingIdx] = useState<number | null>(null)

  const estimatedMinutes = Math.ceil(selectedPersonas.length * questions.length * 3 / 60)

  const generateQuestions = async () => {
    if (!surveyTheme) return
    setGenError(null)
    setGeneratingQuestions(true)
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 15000)
      const res = await fetch('/api/survey/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ persona_ids: [], survey_theme: surveyTheme, questions: null }),
        signal: controller.signal,
      })
      clearTimeout(timeout)
      const reader = res.body?.getReader()
      if (!reader) return
      const dec = new TextDecoder()
      let buf = ''
      let currentEvent = ''
      let currentData = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            currentData = line.slice(6).trim()
          } else if (line === '' && currentEvent && currentData) {
            if (currentEvent === 'questions_generated') {
              const data = JSON.parse(currentData)
              setQuestions(data.questions)
              reader.cancel()
              return
            }
            if (currentEvent === 'survey_complete') {
              reader.cancel()
              return
            }
            currentEvent = ''
            currentData = ''
          }
        }
      }
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

  const handleStart = () => {
    setStep(3)
    startSurvey()
  }

  return (
    <div data-testid="survey-config-screen" className="max-w-2xl space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white">調査設定</h2>
        <div className="text-sm text-gray-500">
          {selectedPersonas.length}名選択済み
        </div>
      </div>

      <div>
        <label className="block text-xs font-semibold text-gray-400 mb-2">
          調査テーマ <span className="text-red-500">*</span>
        </label>
        <textarea
          value={surveyTheme}
          onChange={(e) => setSurveyTheme(e.target.value)}
          placeholder={DEFAULT_THEME}
          rows={3}
          className="w-full bg-[#1c1c2e] border border-[rgba(118,185,0,0.2)] rounded-lg px-4 py-3 text-sm text-gray-200 focus:border-[#76B900] focus:outline-none placeholder-gray-600 resize-none"
        />
      </div>

      <div>
        <label className="block text-xs font-semibold text-gray-400 mb-2">ラベル（任意）</label>
        <input
          type="text"
          value={surveyLabel}
          onChange={(e) => setSurveyLabel(e.target.value)}
          placeholder="例: 投信オンライン_40代男性_東京"
          className="w-full bg-[#1c1c2e] border border-[rgba(118,185,0,0.2)] rounded-lg px-4 py-2.5 text-sm text-gray-200 focus:border-[#76B900] focus:outline-none placeholder-gray-600"
        />
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs font-semibold text-gray-400">質問項目</label>
          <button
            onClick={generateQuestions}
            disabled={!surveyTheme || generatingQuestions}
            className="text-xs text-[#00A3E0] hover:text-[#40c0f0] disabled:opacity-50 transition-colors"
          >
            {generatingQuestions ? '生成中...' : '✨ AIに質問を生成させる'}
          </button>
        </div>
        {llmStatus && !llmStatus.llm_reachable && !llmStatus.mock_llm && (
          <p className="text-yellow-400 text-xs mb-2">
            LLMサーバーに接続できません。モックモードでの実行を検討してください。
          </p>
        )}
        {genError && (
          <p className="text-red-400 text-xs mt-2">{genError}</p>
        )}
        <div className="space-y-2">
          {questions.map((q, i) => (
            <div key={i} className="flex items-start gap-2">
              <span className="text-xs text-gray-600 mt-2.5 w-4 flex-shrink-0">{i + 1}</span>
              {editingIdx === i ? (
                <textarea
                  autoFocus
                  value={q}
                  onChange={(e) => updateQuestion(i, e.target.value)}
                  onBlur={() => setEditingIdx(null)}
                  rows={2}
                  className="flex-1 bg-[#1c1c2e] border border-[#76B900] rounded px-3 py-1.5 text-sm text-gray-200 focus:outline-none resize-none"
                />
              ) : (
                <button
                  onClick={() => setEditingIdx(i)}
                  className="flex-1 text-left bg-[#1c1c2e] border border-[rgba(118,185,0,0.1)] rounded px-3 py-2 text-sm text-gray-300 hover:border-[rgba(118,185,0,0.4)] transition-colors"
                >
                  {q || <span className="text-gray-600">（クリックして編集）</span>}
                </button>
              )}
              <button
                onClick={() => removeQuestion(i)}
                className="mt-1.5 text-gray-600 hover:text-red-400 transition-colors text-lg leading-none"
              >
                ×
              </button>
            </div>
          ))}
          <button
            onClick={addQuestion}
            className="text-xs text-[#76B900] hover:text-[#8fd100] transition-colors mt-1"
          >
            ＋ 質問を追加
          </button>
        </div>
      </div>

      <div className="bg-[#141420] rounded-lg px-4 py-3 text-sm text-gray-400">
        推定所要時間: 約 <span className="text-white font-bold">{estimatedMinutes}分</span>
        <span className="text-gray-600 ml-2">
          ({selectedPersonas.length}名 × {questions.length}問 × ~3秒/回答)
        </span>
      </div>

      <button
        onClick={handleStart}
        disabled={!surveyTheme || questions.length === 0 || selectedPersonas.length === 0}
        className="w-full bg-[#76B900] hover:bg-[#8fd100] disabled:opacity-50 disabled:cursor-not-allowed text-black font-bold py-3 px-6 rounded-lg text-base transition-colors"
      >
        調査を開始する →
      </button>
    </div>
  )
}
