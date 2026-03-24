import { useState, useRef, useEffect } from 'react'
import { useStore } from '../store'
import { api, startFollowupSSE } from '../api'
import PersonaAvatar from './PersonaAvatar'

const FALLBACK_SUGGESTED_QUESTIONS = [
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

function sanitizeSuggestedQuestion(question: string) {
  return question.replace(/（[^）]*）/g, '').trim()
}

function getSuggestedQuestions(sourceQuestions: string[]) {
  const seen = new Set<string>()
  const suggestions: string[] = []

  for (const question of sourceQuestions) {
    const cleaned = sanitizeSuggestedQuestion(question)
    if (!cleaned || seen.has(cleaned)) continue
    seen.add(cleaned)
    suggestions.push(cleaned)
    if (suggestions.length === 3) break
  }

  return suggestions.length > 0 ? suggestions : FALLBACK_SUGGESTED_QUESTIONS
}

function scrollToBottom(container: HTMLDivElement | null) {
  if (!container) return
  if (typeof container.scrollTo === 'function') {
    container.scrollTo({ top: container.scrollHeight, behavior: 'auto' })
    return
  }
  container.scrollTop = container.scrollHeight
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
  const {
    followupPersona,
    currentRunId,
    setStep,
    currentHistoryRun,
    surveyTheme,
    questions,
    openPersonaDetail,
    enableThinking,
    appendFollowupMessages,
    clearFollowupMessages,
  } = useStore()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [profileExpanded, setProfileExpanded] = useState(false)
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([])
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const stickToBottomRef = useRef(true)
  const cancelRef = useRef<(() => void) | null>(null)

  const runId = currentRunId || currentHistoryRun?.id
  useEffect(() => {
    cancelRef.current?.()
    cancelRef.current = null
    setSending(false)
    setInput('')
    setProfileExpanded(false)
    stickToBottomRef.current = true

    if (!followupPersona) {
      setMessages([])
      return
    }

    const existing = currentHistoryRun?.followup_chats[followupPersona.uuid] || []
    setMessages(
      existing.flatMap((msg) =>
        msg.role === 'user' || msg.role === 'assistant'
          ? [{ role: msg.role, content: sanitizeVisibleText(msg.content) } satisfies Message]
          : [],
      ),
    )
  }, [followupPersona, currentHistoryRun])

  useEffect(() => {
    if (stickToBottomRef.current) {
      scrollToBottom(messagesContainerRef.current)
    }
  }, [messages])

  useEffect(() => {
    return () => {
      cancelRef.current?.()
      cancelRef.current = null
    }
  }, [])

  useEffect(() => {
    let active = true
    const fallbackSuggestions = getSuggestedQuestions(currentHistoryRun?.questions ?? questions)

    if (!followupPersona || !runId) {
      setSuggestedQuestions(fallbackSuggestions)
      return () => {
        active = false
      }
    }

    api.getFollowupSuggestions(runId, followupPersona.uuid)
      .then((response) => {
        if (active) {
          setSuggestedQuestions(response.questions.length > 0 ? response.questions : fallbackSuggestions)
        }
      })
      .catch(() => {
        if (active) {
          setSuggestedQuestions(fallbackSuggestions)
        }
      })

    return () => {
      active = false
    }
  }, [followupPersona, runId, currentHistoryRun, questions])

  const send = (text: string) => {
    if (!text.trim() || !followupPersona || !runId || sending) return
    const questionText = text.trim()
    setInput('')
    setSending(true)
    stickToBottomRef.current = true

    const userMsg: Message = { role: 'user', content: questionText }
    const assistantMsg: Message = { role: 'assistant', content: '', streaming: true }
    setMessages((prev) => [...prev, userMsg, assistantMsg])

    cancelRef.current = startFollowupSSE(
      { run_id: runId, persona_uuid: followupPersona.uuid, question: questionText },
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
        const answerText = sanitizeVisibleText(full)
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last.role === 'assistant') {
            return [...prev.slice(0, -1), { ...last, content: answerText, streaming: false }]
          }
          return prev
        })
        appendFollowupMessages(followupPersona.uuid, [
          { role: 'user', content: questionText },
          { role: 'assistant', content: answerText },
        ])
        setSending(false)
        cancelRef.current = null
      },
      (err) => {
        console.error('Followup error:', err)
        const fallbackAnswer = '回答の取得に失敗しました。もう一度お試しください。'
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last?.role === 'assistant' && last.streaming) {
            return [
              ...prev.slice(0, -1),
              {
                role: 'assistant',
                content: fallbackAnswer,
                streaming: false,
              },
            ]
          }
          return prev
        })
        appendFollowupMessages(followupPersona.uuid, [
          { role: 'user', content: questionText },
          { role: 'assistant', content: fallbackAnswer },
        ])
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

  const clearHistory = async () => {
    if (!followupPersona || !runId || sending) return
    if (!window.confirm(`${followupPersona.name} との会話履歴を消去しますか？`)) return

    cancelRef.current?.()
    cancelRef.current = null

    try {
      await api.clearFollowupHistory(runId, followupPersona.uuid)
      setMessages([])
      setInput('')
      setSending(false)
      clearFollowupMessages(followupPersona.uuid)
    } catch (error) {
      console.error('Failed to clear follow-up history:', error)
      setSending(false)
    }
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
    <div data-testid="followup-screen" className="flex h-full min-h-0 flex-col gap-6 xl:flex-row">
      <div className="w-full flex-shrink-0 space-y-4 overflow-y-auto xl:w-72">
        <div className="rounded-[1.75rem] border border-fin-border bg-fin-surface p-4 shadow-card">
          <button
            onClick={() => openPersonaDetail(followupPersona)}
            className="flex items-center gap-3 mb-3 hover:opacity-80 transition-opacity w-full text-left"
            title="プロフィールを表示"
          >
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
          </button>
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

        <div className="rounded-[1.5rem] border border-fin-border bg-fin-panel/55 p-3">
          <div className="mb-2 text-[10px] font-semibold tracking-[0.16em] text-fin-muted">操作</div>
          <div className="flex flex-col gap-2">
            <button
              onClick={() => setStep(4)}
              className="flex items-center justify-between rounded-[1.15rem] border border-fin-border bg-fin-surface px-3 py-2.5 text-left text-sm text-fin-ink shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:border-fin-accent hover:text-fin-accent"
            >
              <span>← レポートに戻る</span>
              <span aria-hidden="true" className="text-[10px] font-semibold tracking-[0.14em] text-fin-muted">TAB 4</span>
            </button>

            <button
              onClick={() => {
                void clearHistory()
              }}
              disabled={sending}
              className="flex items-center justify-between rounded-[1.15rem] border border-fin-danger/30 bg-fin-danger/5 px-3 py-2.5 text-left text-sm text-fin-danger transition-all duration-200 hover:-translate-y-0.5 hover:border-fin-danger hover:bg-fin-danger/10 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span>履歴を消去</span>
              <span aria-hidden="true" className="text-[10px] font-semibold tracking-[0.14em] text-fin-danger/80">RESET</span>
            </button>
          </div>
        </div>

        {theme && (
          <div className="rounded-[1.5rem] border border-fin-border bg-fin-panel/60 p-3">
            <div className="mb-1 text-[10px] tracking-[0.12em] text-fin-muted">調査テーマ</div>
            <div className="text-xs text-fin-ink">{theme}</div>
          </div>
        )}
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[1.75rem] border border-fin-border bg-fin-surface shadow-card">
        <div
          ref={messagesContainerRef}
          data-testid="followup-messages"
          onScroll={(event) => {
            const target = event.currentTarget
            stickToBottomRef.current = target.scrollHeight - target.scrollTop - target.clientHeight < 100
          }}
          className="flex-1 overflow-y-auto p-4 space-y-4"
        >
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
                {enableThinking && msg.role === 'assistant' && msg.thinking && (
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
        </div>

        <div className="flex flex-wrap gap-2 px-4 pb-2">
          {suggestedQuestions.map((q, i) => (
            <button
              key={i}
              onClick={() => send(q)}
              disabled={sending}
              className={`rounded-full border border-fin-border px-3 py-1.5 transition-all duration-200 hover:border-fin-accent hover:text-fin-accent disabled:opacity-50 ${
                messages.length === 0 ? 'text-xs text-fin-ink' : 'text-[11px] text-fin-muted'
              }`}
            >
              {q}
            </button>
          ))}
        </div>

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
