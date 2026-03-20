import { useStore } from '../store'
import PersonaAvatar from './PersonaAvatar'

function sexDisplay(sex: string) {
  return sex === '男' ? '男性' : sex === '女' ? '女性' : sex
}

export default function CompletedFilterReview({ badge }: { badge?: string }) {
  const { selectedPersonas, openPersonaDetail } = useStore()

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h2 className="text-xl font-bold tracking-[-0.03em] text-fin-ink">ペルソナ選択</h2>
        <span className="rounded-full bg-fin-accentSoft px-3 py-1 text-xs font-medium text-fin-accent">
          {badge || '完了済み（閲覧のみ）'}
        </span>
      </div>

      {selectedPersonas.length === 0 ? (
        <div className="rounded-[1.75rem] border border-fin-border bg-fin-panel/60 px-6 py-8 text-center text-sm text-fin-muted">
          ペルソナデータを復元できませんでした
        </div>
      ) : (
        <div>
          <div className="mb-3 text-sm text-fin-muted">{selectedPersonas.length}名 抽出済み</div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {selectedPersonas.map((p) => (
              <button
                key={p.uuid}
                data-testid={`completed-persona-card-${p.uuid}`}
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
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
