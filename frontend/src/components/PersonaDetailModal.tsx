import type { Persona } from '../types'
import PersonaAvatar from './PersonaAvatar'

interface Props {
  persona: Persona | null
  onClose: () => void
}

function Section({ title, content }: { title: string; content?: string }) {
  if (!content) return null
  return (
    <div className="mb-4">
      <div className="mb-1 text-xs font-semibold tracking-[0.12em] text-fin-accent">{title}</div>
      <div className="text-sm leading-relaxed text-fin-ink">{content}</div>
    </div>
  )
}

export default function PersonaDetailModal({ persona, onClose }: Props) {
  if (!persona) return null

  const sexDisplay = persona.sex === '男' ? '男性' : persona.sex === '女' ? '女性' : persona.sex

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-fin-ink/40 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-[2rem] border border-fin-border bg-fin-surface shadow-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 flex items-center gap-3 border-b border-fin-border bg-fin-surface/95 p-5 backdrop-blur">
          <PersonaAvatar name={persona.name} age={persona.age} sex={persona.sex} size={48} />
          <div className="flex-1">
            <div className="text-lg font-bold text-fin-ink">{persona.name}</div>
            <div className="text-sm text-fin-muted">
              {persona.age}歳 · {sexDisplay} · {persona.prefecture}（{persona.region}）
            </div>
            <div className="text-sm text-fin-accent">{persona.occupation}</div>
          </div>
          <button
            onClick={onClose}
            className="text-2xl leading-none text-fin-muted transition-colors hover:text-fin-accent"
          >
            ×
          </button>
        </div>

        <div className="p-5">
          <div className="grid grid-cols-2 gap-2 mb-5 text-sm">
            <div className="rounded-2xl bg-fin-panel px-3 py-2">
              <span className="text-fin-muted">学歴: </span>
              <span className="text-fin-ink">{persona.education_level}</span>
            </div>
            <div className="rounded-2xl bg-fin-panel px-3 py-2">
              <span className="text-fin-muted">婚姻: </span>
              <span className="text-fin-ink">{persona.marital_status}</span>
            </div>
          </div>

          {persona.financial_extension && (
            <div className="mb-5 rounded-[1.5rem] border border-fin-border bg-fin-panel/70 p-4">
              <div className="mb-3 text-xs font-semibold tracking-[0.12em] text-fin-accent">金融プロファイル</div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div><span className="text-fin-muted">リテラシー: </span><span className="text-fin-ink">{persona.financial_extension.financial_literacy}</span></div>
                <div><span className="text-fin-muted">年収帯: </span><span className="text-fin-ink">{persona.financial_extension.annual_income_bracket}</span></div>
                <div><span className="text-fin-muted">資産帯: </span><span className="text-fin-ink">{persona.financial_extension.asset_bracket}</span></div>
                <div><span className="text-fin-muted">取引先: </span><span className="text-fin-ink">{persona.financial_extension.primary_bank_type}</span></div>
                {persona.financial_extension.investment_experience && (
                  <div className="col-span-2"><span className="text-fin-muted">投資経験: </span><span className="text-fin-ink">{persona.financial_extension.investment_experience}</span></div>
                )}
                {persona.financial_extension.financial_concerns && (
                  <div className="col-span-2"><span className="text-fin-muted">懸念事項: </span><span className="text-fin-ink">{persona.financial_extension.financial_concerns}</span></div>
                )}
              </div>
            </div>
          )}

          <Section title="人物像" content={persona.persona} />
          <Section title="職業面" content={persona.professional_persona} />
          <Section title="文化的背景" content={persona.cultural_background} />
          <Section title="スキル・専門性" content={persona.skills_and_expertise} />
          <Section title="趣味・関心事" content={persona.hobbies_and_interests} />
          <Section title="キャリア目標" content={persona.career_goals_and_ambitions} />
          <Section title="スポーツ" content={persona.sports_persona} />
          <Section title="アート" content={persona.arts_persona} />
          <Section title="旅行" content={persona.travel_persona} />
          <Section title="食・料理" content={persona.culinary_persona} />
        </div>
      </div>
    </div>
  )
}
