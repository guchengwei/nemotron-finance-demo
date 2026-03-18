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

function ThinkingBlock({ thinking }: { thinking: string }) {
  return (
    <details className="mb-1.5 group">
      <summary className="text-[10px] text-gray-600 cursor-pointer select-none list-none flex items-center gap-1 hover:text-gray-500 transition-colors w-fit">
        <span className="transition-transform group-open:rotate-90 inline-block">▸</span>
        <span>思考過程</span>
      </summary>
      <div className="mt-1 text-xs text-gray-600 bg-[#0F172A] rounded p-2 whitespace-pre-wrap font-mono leading-relaxed max-h-40 overflow-y-auto">
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

  // Load existing chat history
  useEffect(() => {
    if (!followupPersona || !currentHistoryRun) return
    const existing = currentHistoryRun.followup_chats[followupPersona.uuid] || []
    if (existing.length > 0) {
      setMessages(existing as Message[])
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
    setMessages((prev) => [...prev, userMsg])

    const assistantMsg: Message = { role: 'assistant', content: '', streaming: true }
    setMessages((prev) => [...prev, assistantMsg])

    cancelRef.current = startFollowupSSE(
      { run_id: runId, persona_uuid: followupPersona.uuid, question: text },
      (chunk) => {
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last.role === 'assistant' && last.streaming) {
            return [...prev.slice(0, -1), { ...last, content: last.content + chunk }]
          }
          return prev
        })
      },
      (full) => {
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last.role === 'assistant') {
            return [...prev.slice(0, -1), { ...last, content: full, streaming: false }]
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
            return [...prev.slice(0, -1), { ...last, thinking }]
          }
          return prev
        })
      }
    )
  }

  if (!followupPersona) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4">
        <div className="text-gray-500 text-sm">ペルソナが選択されていません</div>
        <button onClick={() => setStep(4)} className="text-[#0EA5E9] text-sm hover:underline">
          ← レポートに戻る
        </button>
      </div>
    )
  }

  const sexDisplay = followupPersona.sex === '男' ? '男性' : '女性'
  const theme = surveyTheme || currentHistoryRun?.survey_theme

  return (
    <div className="flex gap-6 h-full">
      {/* Left: persona info + survey answers */}
      <div className="w-72 flex-shrink-0 space-y-4 overflow-y-auto">
        {/* Persona card */}
        <div className="bg-[#1E2D40] border border-[rgba(37,99,235,0.15)] rounded-lg p-4">
          <div className="flex items-center gap-3 mb-3">
            <PersonaAvatar
              name={followupPersona.name}
              age={followupPersona.age}
              sex={followupPersona.sex}
              size={44}
            />
            <div>
              <div className="text-base font-bold text-white">{followupPersona.name}</div>
              <div className="text-xs text-gray-500">{followupPersona.age}歳 · {sexDisplay}</div>
              <div className="text-xs text-[#2563EB]">{followupPersona.occupation}</div>
            </div>
          </div>
          <div className="text-xs text-gray-500">{followupPersona.prefecture}（{followupPersona.region}）</div>
          <div className="mt-2">
            <div className={`text-xs text-gray-400 ${profileExpanded ? '' : 'line-clamp-3'}`}>
              {followupPersona.persona}
            </div>
            {followupPersona.persona && followupPersona.persona.length > 120 && (
              <button
                onClick={() => setProfileExpanded(v => !v)}
                className="text-[10px] text-gray-600 hover:text-gray-400 mt-1 transition-colors"
              >
                {profileExpanded ? '▲ 折りたたむ' : '▼ すべて表示'}
              </button>
            )}
          </div>
        </div>

        {/* Back button */}
        <button
          onClick={() => setStep(4)}
          className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
        >
          ← レポートに戻る
        </button>

        {/* Survey context */}
        {theme && (
          <div className="bg-[#1E293B] rounded-lg p-3">
            <div className="text-[10px] text-gray-600 mb-1">調査テーマ</div>
            <div className="text-xs text-gray-400">{theme}</div>
          </div>
        )}
      </div>

      {/* Right: chat */}
      <div className="flex-1 flex flex-col bg-[#1E293B] rounded-xl overflow-hidden">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="text-center text-gray-600 text-sm py-8">
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
                  className={`px-4 py-2.5 rounded-2xl text-sm ${
                    msg.role === 'user'
                      ? 'bg-[#2563EB] text-black rounded-br-sm'
                      : 'bg-[#1E2D40] text-gray-200 rounded-bl-sm'
                  } ${msg.streaming ? 'cursor-blink' : ''}`}
                >
                  {msg.content || (msg.streaming ? '' : '（空の回答）')}
                </div>
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Suggested questions */}
        {messages.length === 0 && (
          <div className="px-4 pb-2 flex flex-wrap gap-2">
            {SUGGESTED_QUESTIONS.map((q, i) => (
              <button
                key={i}
                onClick={() => send(q)}
                className="text-xs text-[#0EA5E9] border border-[rgba(0,163,224,0.2)] px-3 py-1.5 rounded-full
                  hover:border-[#0EA5E9] hover:bg-[#0EA5E9]/5 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        )}

        {/* Input */}
        <div className="p-4 border-t border-[rgba(255,255,255,0.05)] flex gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
            placeholder={`${followupPersona.name} に質問する...`}
            disabled={sending}
            className="flex-1 bg-[#1E2D40] border border-[rgba(37,99,235,0.15)] rounded-lg px-4 py-2.5 text-sm text-gray-200
              focus:border-[#2563EB] focus:outline-none placeholder-gray-600 disabled:opacity-50"
          />
          <button
            onClick={() => send(input)}
            disabled={!input.trim() || sending}
            className="bg-[#2563EB] hover:bg-[#3B82F6] disabled:opacity-50 text-black font-bold px-4 py-2.5 rounded-lg text-sm transition-colors"
          >
            送信
          </button>
        </div>
      </div>
    </div>
  )
}
