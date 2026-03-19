import { useState, useEffect } from 'react'
import { useStore } from './store'
import { api } from './api'
import { useSurvey } from './hooks/useSurvey'
import Layout from './components/Layout'
import CompletedFilterReview from './components/CompletedFilterReview'
import FilterPanel from './components/FilterPanel'
import SurveyConfig from './components/SurveyConfig'
import SurveyRunner from './components/SurveyRunner'
import ReportDashboard from './components/ReportDashboard'
import FollowUpChat from './components/FollowUpChat'

const QUICK_DEMO_THEME = 'AIを活用した資産運用アドバイザリーサービスの導入に対する金融機関顧客の反応'
const QUICK_DEMO_QUESTIONS = [
  'AIによる資産運用アドバイスに対する全体的な関心度を教えてください（1:全く関心がない〜5:非常に関心がある）',
  'AIアドバイザーに最も期待する機能は何ですか？',
  '利用にあたっての懸念点をお聞かせください',
]

function QuickDemoButton() {
  const store = useStore()
  const { startSurvey } = useSurvey()
  const [loading, setLoading] = useState(false)

  const handleQuickDemo = async () => {
    setLoading(true)
    try {
      const result = await api.getSample({ count: 8 })
      store.setSelectedPersonas(result.sampled)
      store.setSurveyTheme(QUICK_DEMO_THEME)
      store.setQuestions(QUICK_DEMO_QUESTIONS)
      store.setSurveyLabel('クイックデモ')
      store.setStep(3)
      startSurvey()
    } catch (e) {
      console.error('Quick demo failed:', e)
      setLoading(false)
    }
  }

  return (
    <button
      data-testid="quick-demo-button"
      onClick={handleQuickDemo}
      disabled={loading}
      className="rounded-full bg-fin-accent px-6 py-3 text-sm font-semibold text-fin-surface transition-all duration-200 hover:-translate-y-0.5 hover:bg-fin-accentStrong disabled:opacity-70"
    >
      {loading ? '起動中...' : 'デモを実行'}
    </button>
  )
}

function WelcomeScreen() {
  return (
    <div className="flex flex-col items-center justify-center h-64 gap-6 text-center">
      <div>
        <div className="mb-2 text-balance text-3xl font-extrabold tracking-[-0.04em] text-fin-ink">
          Nemotron Financial Survey Demo
        </div>
        <div className="mx-auto max-w-md text-sm leading-6 text-fin-muted">
          NVIDIA Nemotron-Personas-Japan × Nemotron-Nano-9B-v2 を使用した<br />
          金融サービスAIリサーチデモ
        </div>
      </div>
      <div className="flex flex-col gap-4 sm:flex-row">
        <QuickDemoButton />
        <button
          data-testid="custom-survey-button"
          onClick={() => useStore.getState().setStep(2)}
          className="rounded-full border border-fin-border bg-fin-surface px-6 py-3 text-sm font-semibold text-fin-ink transition-all duration-200 hover:-translate-y-0.5 hover:border-fin-accent hover:text-fin-accent"
        >
          カスタム調査を始める
        </button>
      </div>
    </div>
  )
}

export default function App() {
  const { currentStep, resetVersion } = useStore()
  const currentHistoryRun = useStore(s => s.currentHistoryRun)
  const dbReady = useStore(s => s.dbReady)
  const setDbReady = useStore(s => s.setDbReady)
  const setLlmStatus = useStore(s => s.setLlmStatus)
  const [dbError, setDbError] = useState<string | null>(null);

  useEffect(() => {
    if (dbReady) return;
    let cancelled = false;
    const poll = async () => {
      while (!cancelled) {
        const result = await api.checkReady();
        if (cancelled) return;
        if (result.error) {
          setDbError(result.error);
          return;
        }
        if (result.ready) {
          setDbReady(true);
          const health = await api.checkHealth();
          setLlmStatus(health);
          return;
        }
        await new Promise(r => setTimeout(r, 2000));
      }
    };
    poll();
    return () => { cancelled = true; };
  }, [dbReady, setDbReady, setLlmStatus]);

  if (!dbReady) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-fin-canvas px-6">
        <div className="rounded-[2rem] border border-fin-border bg-fin-surface px-10 py-12 text-center shadow-panel">
          {dbError ? (
            <>
              <div className="mx-auto mb-4 flex h-10 w-10 items-center justify-center rounded-full bg-fin-danger/10 text-2xl text-fin-danger">!</div>
              <p className="font-semibold text-fin-danger">データベースの初期化に失敗しました</p>
              <p className="mt-2 max-w-md text-sm text-fin-muted">{dbError}</p>
            </>
          ) : (
            <>
              <div className="mx-auto mb-4 h-9 w-9 animate-spin rounded-full border-2 border-fin-accent/20 border-t-fin-accent" />
              <p className="font-medium text-fin-ink">データベースを準備中...</p>
              <p className="mt-2 text-sm text-fin-muted">初回は数分かかる場合があります</p>
            </>
          )}
        </div>
      </div>
    );
  }

  const renderStep = () => {
    switch (currentStep) {
      case 1:
        if (currentHistoryRun?.status === 'completed') {
          return <CompletedFilterReview />
        }
        return (
          <div>
            <WelcomeScreen />
            <div className="mt-8">
              <FilterPanel key={resetVersion} />
            </div>
          </div>
        )
      case 2:
        return <SurveyConfig />
      case 3:
        return <SurveyRunner />
      case 4:
        return <ReportDashboard />
      case 5:
        return <FollowUpChat />
      default:
        return null
    }
  }

  return <Layout>{renderStep()}</Layout>
}
