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
      <div className="text-xs font-semibold text-[#76B900] mb-1">{title}</div>
      <div className="text-sm text-gray-300 leading-relaxed">{content}</div>
    </div>
  )
}

export default function PersonaDetailModal({ persona, onClose }: Props) {
  if (!persona) return null

  const sexDisplay = persona.sex === '男' ? '男性' : persona.sex === '女' ? '女性' : persona.sex

  return (
    <div
      className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-[#1c1c2e] border border-[rgba(118,185,0,0.2)] rounded-lg w-full max-w-2xl max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 p-5 border-b border-[rgba(118,185,0,0.1)] sticky top-0 bg-[#1c1c2e]">
          <PersonaAvatar name={persona.name} age={persona.age} sex={persona.sex} size={48} />
          <div className="flex-1">
            <div className="text-lg font-bold text-white">{persona.name}</div>
            <div className="text-sm text-gray-400">
              {persona.age}歳 · {sexDisplay} · {persona.prefecture}（{persona.region}）
            </div>
            <div className="text-sm text-[#76B900]">{persona.occupation}</div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white text-2xl leading-none"
          >
            ×
          </button>
        </div>

        {/* Content */}
        <div className="p-5">
          {/* Basic info */}
          <div className="grid grid-cols-2 gap-2 mb-5 text-sm">
            <div className="bg-[#141420] rounded p-2">
              <span className="text-gray-500">学歴: </span>
              <span className="text-gray-200">{persona.education_level}</span>
            </div>
            <div className="bg-[#141420] rounded p-2">
              <span className="text-gray-500">婚姻: </span>
              <span className="text-gray-200">{persona.marital_status}</span>
            </div>
          </div>

          {/* Financial extension */}
          {persona.financial_extension && (
            <div className="bg-[#141420] rounded-lg p-4 mb-5 border border-[rgba(118,185,0,0.15)]">
              <div className="text-xs font-semibold text-[#76B900] mb-3">金融プロファイル</div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div><span className="text-gray-500">リテラシー: </span><span className="text-white">{persona.financial_extension.financial_literacy}</span></div>
                <div><span className="text-gray-500">年収帯: </span><span className="text-white">{persona.financial_extension.annual_income_bracket}</span></div>
                <div><span className="text-gray-500">資産帯: </span><span className="text-white">{persona.financial_extension.asset_bracket}</span></div>
                <div><span className="text-gray-500">取引先: </span><span className="text-white">{persona.financial_extension.primary_bank_type}</span></div>
                {persona.financial_extension.investment_experience && (
                  <div className="col-span-2"><span className="text-gray-500">投資経験: </span><span className="text-gray-300">{persona.financial_extension.investment_experience}</span></div>
                )}
                {persona.financial_extension.financial_concerns && (
                  <div className="col-span-2"><span className="text-gray-500">懸念事項: </span><span className="text-gray-300">{persona.financial_extension.financial_concerns}</span></div>
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
