import type { TopPick, Persona } from '../types'
import PersonaAvatar from './PersonaAvatar'

interface Props {
  pick: TopPick
  persona?: Persona
  variant: 'positive' | 'negative' | 'unique'
  onChat?: () => void
}

const VARIANT_LABELS = {
  positive: { label: 'ポジティブ', color: 'text-green-400 bg-green-400/10' },
  negative: { label: 'ネガティブ', color: 'text-orange-400 bg-orange-400/10' },
  unique: { label: 'ユニーク', color: 'text-[#0EA5E9] bg-[#0EA5E9]/10' },
}

export default function TopPickCard({ pick, persona, variant, onChat }: Props) {
  const v = VARIANT_LABELS[variant]
  const age = persona?.age || 30
  const sex = persona?.sex || '男'

  return (
    <div className="bg-[#1E2D40] border border-[rgba(37,99,235,0.15)] rounded-lg p-4 space-y-3">
      {/* Variant badge */}
      <span className={`text-[10px] font-bold px-2 py-1 rounded ${v.color}`}>
        {v.label}
      </span>

      {/* Persona info */}
      <div className="flex items-center gap-3">
        <PersonaAvatar name={pick.persona_name} age={age} sex={sex} size={36} />
        <div>
          <div className="text-sm font-bold text-white">{pick.persona_name}</div>
          <div className="text-xs text-gray-500">{pick.persona_summary}</div>
        </div>
      </div>

      {/* Highlight reason */}
      <div className="text-xs text-gray-500">{pick.highlight_reason}</div>

      {/* Quote */}
      <blockquote className="border-l-2 border-[#2563EB] pl-3 text-sm text-gray-300 italic">
        「{pick.highlight_quote}」
      </blockquote>

      {/* Chat button */}
      {onChat && (
        <button
          data-testid={`top-pick-chat-${pick.persona_uuid}`}
          onClick={onChat}
          className="w-full text-center text-xs text-[#0EA5E9] hover:text-[#38BDF8] py-1.5 border border-[rgba(0,163,224,0.2)] rounded hover:border-[#0EA5E9] transition-colors"
        >
          この人に質問する →
        </button>
      )}
    </div>
  )
}
