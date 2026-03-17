import { useState } from 'react'
import type { Persona } from '../types'
import PersonaAvatar from './PersonaAvatar'
import PersonaDetailModal from './PersonaDetailModal'

interface Props {
  personas: Persona[]
  maxVisible?: number
}

function SkillTags({ listStr }: { listStr?: string }) {
  if (!listStr) return null
  try {
    // Python-style list string: "['tag1', 'tag2']"
    const tags = listStr
      .replace(/^\[|\]$/g, '')
      .split(',')
      .map((s) => s.trim().replace(/^['"]|['"]$/g, ''))
      .filter(Boolean)
      .slice(0, 4)

    return (
      <div className="flex flex-wrap gap-1 mt-1">
        {tags.map((tag, i) => (
          <span key={i} className="text-[10px] bg-[#76B900]/10 text-[#76B900] px-1.5 py-0.5 rounded">
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
  const [selected, setSelected] = useState<Persona | null>(null)
  const visible = personas.slice(0, maxVisible)
  const remaining = personas.length - maxVisible

  const sexDisplay = (sex: string) => sex === '男' ? '男性' : sex === '女' ? '女性' : sex

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {visible.map((p) => (
          <button
            key={p.uuid}
            onClick={() => setSelected(p)}
            className="text-left bg-[#1c1c2e] border border-[rgba(118,185,0,0.1)] rounded-lg p-3
              hover:border-[rgba(118,185,0,0.4)] hover:bg-[#242438] transition-all fade-in"
          >
            <div className="flex items-center gap-2 mb-2">
              <PersonaAvatar name={p.name} age={p.age} sex={p.sex} size={32} />
              <div className="min-w-0">
                <div className="text-sm font-semibold text-white truncate">{p.name}</div>
                <div className="text-[10px] text-gray-500">{p.age}歳 · {sexDisplay(p.sex)}</div>
              </div>
            </div>
            <div className="text-[11px] text-[#76B900] truncate mb-1">{p.occupation}</div>
            <div className="text-[10px] text-gray-500 truncate">{p.prefecture}（{p.region}）</div>
            <div className="text-[10px] text-gray-400 mt-1 line-clamp-2">{p.persona.slice(0, 60)}...</div>
            <SkillTags listStr={p.skills_and_expertise_list} />
          </button>
        ))}
        {remaining > 0 && (
          <div className="bg-[#1c1c2e] border border-[rgba(118,185,0,0.1)] rounded-lg p-3 flex items-center justify-center">
            <span className="text-gray-500 text-sm">他 {remaining} 名...</span>
          </div>
        )}
      </div>

      <PersonaDetailModal persona={selected} onClose={() => setSelected(null)} />
    </>
  )
}
