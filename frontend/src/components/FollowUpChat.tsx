import { useState, useRef, useEffect } from 'react'
import { useStore } from '../store'
import { startFollowupSSE } from '../api'
import PersonaAvatar from './PersonaAvatar'

const SUGGESTED_QUESTIONS = [
  '具体的にどの程度の手数料なら許容できますか？',
  'どのような情報があれば判断しやすいですか？',
  'このサービスを知人に勧めますか？その理由は？',
]

interface Message {
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  thinking?: string
}

function sanitizeVisibleText(text: string) {
  return text.replace(/<\/?think>/gi, '').trim()
}

function ThinkingBlock({ thinking }: { thinking: string }) {
  return (
    <details data-testid="followup-thinking-block" className="mb-1.5 group">
      <summary className="flex w-fit cursor-pointer list-none items-center gap-1 select-none text-[10px] text-fin-muted transition-colors hover:text-fin-accent">
        <span className="transition-transform group-open:rotate-90 inline-block">▸</span>
        <span>思考過程</span>
      </summary>
      <div className="mt-1 max-h-40 overflow-y-auto rounded-2xl border border-fin-border bg-fin-panel p-3 font-mono text-xs leading-relaxed text-fin-ink whitespace-pre-wrap">
        {thinking}
      </div>
    </details>
  )
}

export default function FollowUpChat() {
  const { followupPersona, currentRunId, setStep, currentHistoryRun, surveyTheme } = useStore()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [profileExpanded, setProfileExpanded] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const cancelRef = useRef<(() => void) | null>(null)

  const runId = currentRunId || currentHistoryRun?.id

  useEffect(() => {
    if (!followupPersona || !currentHistoryRun) return
    const existing = currentHistoryRun.followup_chats[followupPersona.uuid] || []
    if (existing.length > 0) {
      setMessages(existing.map((msg) => ({ ...msg, content: sanitizeVisibleText(msg.content) })) as Message[])
    }
  }, [followupPersona, currentHistoryRun])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = (text: string) => {
    if (!text.trim() || !followupPersona || !runId || sending) return
    setInput('')
    setSending(true)

    const userMsg: Message = { role: 'user', content: text }
    const assistantMsg: Message = { role: 'assistant', content: '', streaming: true }
    setMessages((prev) => [...prev, userMsg, assistantMsg])

    cancelRef.current = startFollowupSSE(
      { run_id: runId, persona_uuid: followupPersona.uuid, question: text },
      (chunk) => {
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last.role === 'assistant' && last.streaming) {
            return [...prev.slice(0, -1), { ...last, content: sanitizeVisibleText(last.content + chunk) }]
          }
          return prev
        })
      },
      (full) => {
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last.role === 'assistant') {
            return [...prev.slice(0, -1), { ...last, content: sanitizeVisibleText(full), streaming: false }]
          }
          return prev
        })
        setSending(false)
        cancelRef.current = null
      },
      (err) => {
        console.error('Followup error:', err)
        setSending(false)
        cancelRef.current = null
      },
      (thinking) => {
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last.role === 'assistant' && last.streaming) {
            return [...prev.slice(0, -1), { ...last, thinking: sanitizeVisibleText(thinking) }]
          }
          return prev
        })
      },
    )
  }

  if (!followupPersona) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <div className="text-sm text-fin-muted">ペルソナが選択されていません</div>
        <button onClick={() => setStep(4)} className="text-sm text-fin-accent hover:underline">
          ← レポートに戻る
        </button>
      </div>
    )
  }

  const sexDisplay = followupPersona.sex === '男' ? '男性' : '女性'
  const theme = surveyTheme || currentHistoryRun?.survey_theme

  return (
    <div data-testid="followup-screen" className="flex h-full flex-col gap-6 xl:flex-row">
      <div className="w-full flex-shrink-0 space-y-4 overflow-y-auto xl:w-72">
        <div className="rounded-[1.75rem] border border-fin-border bg-fin-surface p-4 shadow-card">
          <div className="flex items-center gap-3 mb-3">
            <PersonaAvatar
              name={followupPersona.name}
              age={followupPersona.age}
              sex={followupPersona.sex}
              size={44}
            />
            <div>
              <div className="text-base font-bold text-fin-ink">{followupPersona.name}</div>
              <div className="text-xs text-fin-muted">{followupPersona.age}歳 · {sexDisplay}</div>
              <div className="text-xs text-fin-accent">{followupPersona.occupation}</div>
            </div>
          </div>
          <div className="text-xs text-fin-muted">{followupPersona.prefecture}（{followupPersona.region}）</div>
          <div className="mt-3">
            <div
              data-testid="followup-profile-text"
              className={`text-xs text-fin-ink whitespace-pre-wrap transition-all ${profileExpanded ? '' : 'max-h-24 overflow-hidden'}`}
            >
              {followupPersona.persona}
            </div>
            {followupPersona.persona && (
              <button
                data-testid="followup-profile-toggle"
                onClick={() => setProfileExpanded((v) => !v)}
                className="mt-2 text-[10px] text-fin-muted transition-colors hover:text-fin-accent"
              >
                {profileExpanded ? '▲ 折りたたむ' : '▼ すべて表示'}
              </button>
            )}
          </div>
        </div>

        <button
          onClick={() => setStep(4)}
          className="text-xs text-fin-muted transition-colors hover:text-fin-accent"
        >
          ← レポートに戻る
        </button>

        {theme && (
          <div className="rounded-[1.5rem] border border-fin-border bg-fin-panel/60 p-3">
            <div className="mb-1 text-[10px] tracking-[0.12em] text-fin-muted">調査テーマ</div>
            <div className="text-xs text-fin-ink">{theme}</div>
          </div>
        )}
      </div>

      <div className="flex min-h-[32rem] flex-1 flex-col overflow-hidden rounded-[1.75rem] border border-fin-border bg-fin-surface shadow-card">
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="py-8 text-center text-sm text-fin-muted">
              {followupPersona.name} に質問してみましょう
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`fade-in flex items-end gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role === 'assistant' && (
                <PersonaAvatar
                  name={followupPersona.name}
                  age={followupPersona.age}
                  sex={followupPersona.sex}
                  size={28}
                />
              )}
              <div className="max-w-lg">
                {msg.role === 'assistant' && msg.thinking && (
                  <ThinkingBlock thinking={msg.thinking} />
                )}
                <div
                  data-testid={msg.role === 'assistant' ? 'followup-answer-bubble' : undefined}
                  className={`px-4 py-2.5 rounded-2xl text-sm whitespace-pre-wrap ${
                    msg.role === 'user'
                      ? 'rounded-br-sm bg-fin-accent text-fin-surface'
                      : 'rounded-bl-sm border border-fin-border bg-fin-panel text-fin-ink'
                  } ${msg.streaming ? 'cursor-blink' : ''}`}
                >
                  {sanitizeVisibleText(msg.content) || (msg.streaming ? (
                    <span className="thinking-dots text-fin-accent">
                      <span>思考中</span><span>.</span><span>.</span><span>.</span>
                    </span>
                  ) : '（空の回答）')}
                </div>
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {messages.length === 0 && (
          <div className="px-4 pb-2 flex flex-wrap gap-2">
            {SUGGESTED_QUESTIONS.map((q, i) => (
              <button
                key={i}
                onClick={() => send(q)}
                className="rounded-full border border-fin-border px-3 py-1.5 text-xs text-fin-ink transition-all duration-200 hover:-translate-y-0.5 hover:border-fin-accent hover:text-fin-accent"
              >
                {q}
              </button>
            ))}
          </div>
        )}

        <div className="flex gap-3 border-t border-fin-border p-4">
          <input
            data-testid="followup-input"
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
            placeholder={`${followupPersona.name} に質問する...`}
            disabled={sending}
            className="flex-1 rounded-full border border-fin-border bg-fin-panel px-4 py-2.5 text-sm text-fin-ink transition-colors placeholder:text-fin-muted focus:border-fin-accent focus:outline-none disabled:opacity-50"
          />
          <button
            onClick={() => send(input)}
            disabled={!input.trim() || sending}
            className="rounded-full bg-fin-accent px-4 py-2.5 text-sm font-semibold text-fin-surface transition-all duration-200 hover:-translate-y-0.5 hover:bg-fin-accentStrong disabled:opacity-50"
          >
            送信
          </button>
        </div>
      </div>
    </div>
  )
}
