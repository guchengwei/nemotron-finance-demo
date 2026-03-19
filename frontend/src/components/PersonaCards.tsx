import { useStore } from '../store'
import type { Persona } from '../types'
import PersonaAvatar from './PersonaAvatar'

interface Props {
  personas: Persona[]
  maxVisible?: number
}

function SkillTags({ listStr }: { listStr?: string }) {
  if (!listStr) return null
  try {
    const tags = listStr
      .replace(/^\[|\]$/g, '')
      .split(',')
      .map((s) => s.trim().replace(/^['"]|['"]$/g, ''))
      .filter(Boolean)
      .slice(0, 4)

    return (
      <div className="flex flex-wrap gap-1 mt-1">
        {tags.map((tag, i) => (
          <span key={i} className="rounded-full bg-fin-accentSoft px-1.5 py-0.5 text-[10px] text-fin-accent">
            {tag}
          </span>
        ))}
      </div>
    )
  } catch {
    return null
  }
}

export default function PersonaCards({ personas, maxVisible = 20 }: Props) {
  const { openPersonaDetail } = useStore()
  const visible = personas.slice(0, maxVisible)
  const remaining = personas.length - maxVisible

  const sexDisplay = (sex: string) => sex === '男' ? '男性' : sex === '女' ? '女性' : sex

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
      {visible.map((p) => (
        <button
          key={p.uuid}
          onClick={() => openPersonaDetail(p)}
          className="fade-in rounded-[1.5rem] border border-fin-border bg-fin-surface p-4 text-left shadow-card transition-all duration-200 hover:-translate-y-1 hover:border-fin-accent/35 hover:bg-fin-panel/60"
        >
          <div className="flex items-center gap-2 mb-2">
            <PersonaAvatar name={p.name} age={p.age} sex={p.sex} size={32} />
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-fin-ink">{p.name}</div>
              <div className="text-[10px] text-fin-muted">{p.age}歳 · {sexDisplay(p.sex)}</div>
            </div>
          </div>
          <div className="mb-1 truncate text-[11px] font-medium text-fin-accent">{p.occupation}</div>
          <div className="truncate text-[10px] text-fin-muted">{p.prefecture}（{p.region}）</div>
          {p.financial_extension?.financial_literacy && (
            <div className="mt-1">
              <span className="rounded-full bg-fin-panel border border-fin-border px-1.5 py-0.5 text-[10px] text-fin-muted">
                {p.financial_extension.financial_literacy}
              </span>
            </div>
          )}
          <div className="mt-1 line-clamp-2 text-[10px] text-fin-muted/90">{p.persona.slice(0, 60)}...</div>
          <SkillTags listStr={p.skills_and_expertise_list} />
        </button>
      ))}
      {remaining > 0 && (
        <div className="flex items-center justify-center rounded-[1.5rem] border border-dashed border-fin-border bg-fin-panel/60 p-3">
          <span className="text-sm text-fin-muted">他 {remaining} 名...</span>
        </div>
      )}
    </div>
  )
}
