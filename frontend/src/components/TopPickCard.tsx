import type { TopPick, Persona } from '../types'
import PersonaAvatar from './PersonaAvatar'

interface Props {
  pick: TopPick
  persona?: Persona
  variant: 'positive' | 'negative' | 'unique'
  onChat?: () => void
  onProfile?: () => void
}

const VARIANT_LABELS = {
  positive: { label: 'ポジティブ', color: 'text-fin-success bg-fin-success/10' },
  negative: { label: 'ネガティブ', color: 'text-fin-warning bg-fin-warning/10' },
  unique: { label: 'ユニーク', color: 'text-fin-accent bg-fin-accentSoft' },
}

export default function TopPickCard({ pick, persona, variant, onChat, onProfile }: Props) {
  const v = VARIANT_LABELS[variant]
  const age = persona?.age || 30
  const sex = persona?.sex || '男'

  return (
    <div className="space-y-3 rounded-[1.5rem] border border-fin-border bg-fin-surface p-4 shadow-card">
      <span className={`rounded-full px-2 py-1 text-[10px] font-bold ${v.color}`}>
        {v.label}
      </span>

      <div className="flex items-center gap-3">
        <PersonaAvatar name={pick.persona_name} age={age} sex={sex} size={36} />
        <div>
          <div className="text-sm font-bold text-fin-ink">{pick.persona_name}</div>
          <div className="text-xs text-fin-muted">{pick.persona_summary}</div>
        </div>
      </div>

      <div className="text-xs text-fin-muted">{pick.highlight_reason}</div>

      <blockquote className="border-l-2 border-fin-accent pl-3 text-sm italic text-fin-ink">
        「{pick.highlight_quote}」
      </blockquote>

      {onProfile && (
        <button
          data-testid={`top-pick-profile-${pick.persona_uuid}`}
          onClick={onProfile}
          className="w-full rounded-full border border-fin-border/60 py-1.5 text-center text-xs font-medium text-fin-muted transition-all duration-200 hover:-translate-y-0.5 hover:border-fin-accent/40 hover:text-fin-accent"
        >
          プロフィールを見る
        </button>
      )}
      {onChat && (
        <button
          data-testid={`top-pick-chat-${pick.persona_uuid}`}
          onClick={onChat}
          className="w-full rounded-full border border-fin-border py-2 text-center text-xs font-medium text-fin-ink transition-all duration-200 hover:-translate-y-0.5 hover:border-fin-accent hover:text-fin-accent"
        >
          この人に質問する →
        </button>
      )}
    </div>
  )
}
