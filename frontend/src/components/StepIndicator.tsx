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
    <div className="flex items-center gap-0">
      {STEPS.map((step, i) => {
        const isActive = step.id === currentStep
        const isDone = step.id < currentStep
        const canNav = canNavigateTo(step.id)

        return (
          <div key={step.id} className="flex items-center">
            <button
              onClick={() => canNav && setStep(step.id)}
              disabled={!canNav}
              className={`flex items-center gap-2 px-3 py-1.5 rounded text-xs font-medium transition-colors
                ${isActive
                  ? 'bg-[#2563EB] text-black'
                  : isDone && canNav
                  ? 'text-[#2563EB] hover:bg-[#2563EB]/10 cursor-pointer'
                  : canNav
                  ? 'text-gray-400 hover:bg-white/5 cursor-pointer'
                  : 'text-gray-600 cursor-not-allowed'
                }`}
            >
              <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold
                ${isActive ? 'bg-black/20' : isDone ? 'bg-[#2563EB]/20' : 'bg-white/10'}`}
              >
                {isDone ? '✓' : step.id}
              </span>
              {step.label}
            </button>
            {i < STEPS.length - 1 && (
              <span className="text-gray-700 mx-1">›</span>
            )}
          </div>
        )
      })}
    </div>
  )
}
