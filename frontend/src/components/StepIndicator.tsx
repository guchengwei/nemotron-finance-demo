import { useStore, type Step } from '../store'

const STEPS: { id: Step; label: string }[] = [
  { id: 1, label: 'ペルソナ選択' },
  { id: 2, label: '調査設定' },
  { id: 3, label: '調査実行' },
  { id: 4, label: 'レポート' },
  { id: 5, label: '深掘り' },
]

export default function StepIndicator() {
  const { currentStep, setStep, surveyComplete } = useStore()

  const canNavigateTo = (step: Step): boolean => {
    if (step === 1) return true
    if (step === 2) return useStore.getState().selectedPersonas.length > 0
    if (step === 3) return false  // only via survey start
    if (step === 4) return surveyComplete || useStore.getState().currentReport !== null
    if (step === 5) return useStore.getState().currentReport !== null
    return false
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {STEPS.map((step, i) => {
        const isActive = step.id === currentStep
        const isDone = step.id < currentStep
        const canNav = canNavigateTo(step.id)

        return (
          <div key={step.id} className="flex items-center">
            <button
              onClick={() => canNav && setStep(step.id)}
              disabled={!canNav}
              className={`flex items-center gap-2 rounded-full border px-3 py-2 text-xs font-medium transition-all duration-200
                ${isActive
                  ? 'border-fin-accent bg-fin-accent text-fin-surface'
                  : isDone && canNav
                  ? 'border-fin-accent/20 bg-fin-accentSoft text-fin-accent hover:-translate-y-0.5'
                  : canNav
                  ? 'border-fin-border bg-fin-surface text-fin-muted hover:-translate-y-0.5 hover:border-fin-accent/40 hover:text-fin-accent'
                  : 'cursor-not-allowed border-fin-border/70 bg-fin-surface text-fin-muted/70'
                }`}
            >
              <span className={`flex h-5 w-5 items-center justify-center rounded-full text-xs font-bold
                ${isActive ? 'bg-white/15' : isDone ? 'bg-fin-surface/80' : 'bg-fin-panel/70'}`}
              >
                {isDone ? '✓' : step.id}
              </span>
              {step.label}
            </button>
            {i < STEPS.length - 1 && (
              <span className="mx-2 text-fin-muted">›</span>
            )}
          </div>
        )
      })}
    </div>
  )
}
