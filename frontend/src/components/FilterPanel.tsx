import { useEffect, useMemo, useRef, useState } from 'react'
import { useStore } from '../store'
import { api } from '../api'
import type { Persona } from '../types'
import PersonaCards from './PersonaCards'

const COUNT_PRESETS = [
  { label: '高速デモ (8名)', value: 8 },
  { label: '標準 (30名)', value: 30 },
  { label: 'フル調査 (100名)', value: 100 },
]

export default function FilterPanel() {
  const { filters, setFilters, setSelectedPersonas, setStep } = useStore()

  const [sex, setSex] = useState('')
  const [ageMin, setAgeMin] = useState(20)
  const [ageMax, setAgeMax] = useState(80)
  const [region, setRegion] = useState('')
  const [prefecture, setPrefecture] = useState('')
  const [occupation, setOccupation] = useState('')
  const [education, setEducation] = useState('')
  const [financialLiteracy, setFinancialLiteracy] = useState('')
  const [count, setCount] = useState(8)
  const [customCount, setCustomCount] = useState('')

  const [filtersLoading, setFiltersLoading] = useState(!filters)
  const [sampling, setSampling] = useState(false)
  const [matchCount, setMatchCount] = useState<number | null>(filters?.total_count ?? null)
  const [countLoading, setCountLoading] = useState(false)
  const [personas, setPersonas] = useState<Persona[]>([])
  const latestCountRequest = useRef(0)

  const queryParams = useMemo(() => ({
    sex: sex || undefined,
    age_min: ageMin,
    age_max: ageMax,
    region: region || undefined,
    prefecture: prefecture || undefined,
    occupation: occupation || undefined,
    education: education || undefined,
    financial_literacy: financialLiteracy || undefined,
  }), [sex, ageMin, ageMax, region, prefecture, occupation, education, financialLiteracy])

  useEffect(() => {
    let active = true

    if (filters) {
      setFiltersLoading(false)
      setMatchCount(filters.total_count)
      return
    }

    setFiltersLoading(true)
    api.getFilters().then((response) => {
      if (!active) return
      setFilters(response)
      setMatchCount(response.total_count)
      setFiltersLoading(false)
    }).catch((error) => {
      if (!active) return
      console.error(error)
      setFiltersLoading(false)
    })

    return () => {
      active = false
    }
  }, [filters, setFilters])

  useEffect(() => {
    if (!filters) return

    const isDefaultFilterState = (
      !sex &&
      ageMin === 20 &&
      ageMax === 80 &&
      !region &&
      !prefecture &&
      !occupation &&
      !education &&
      !financialLiteracy
    )

    if (isDefaultFilterState) {
      setMatchCount(filters.total_count)
      setCountLoading(false)
      return
    }

    const controller = new AbortController()
    const requestId = latestCountRequest.current + 1
    latestCountRequest.current = requestId
    const timeoutId = window.setTimeout(() => {
      setCountLoading(true)
      api.getCount(queryParams, controller.signal).then((result) => {
        if (latestCountRequest.current !== requestId) return
        setMatchCount(result.total_matching)
        setCountLoading(false)
      }).catch((error) => {
        if ((error as Error).name === 'AbortError') return
        if (latestCountRequest.current !== requestId) return
        console.error(error)
        setCountLoading(false)
      })
    }, 250)

    return () => {
      window.clearTimeout(timeoutId)
      controller.abort()
    }
  }, [filters, queryParams, sex, ageMin, ageMax, region, prefecture, occupation, education, financialLiteracy])

  const resolvedCount = (() => {
    if (!customCount.trim()) return count
    const parsed = Number.parseInt(customCount, 10)
    if (Number.isNaN(parsed)) return count
    return Math.min(200, Math.max(1, parsed))
  })()

  const handleSample = async () => {
    setSampling(true)
    try {
      const result = await api.getSample({
        ...queryParams,
        count: resolvedCount,
      })
      setPersonas(result.sampled)
      setSelectedPersonas(result.sampled)
      setMatchCount(result.total_matching)
    } catch (e) {
      console.error(e)
    } finally {
      setSampling(false)
    }
  }

  if (filtersLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <div data-testid="filters-loading" className="text-sm text-fin-muted">データベース読み込み中...</div>
      </div>
    )
  }

  if (!filters) {
    return null
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold tracking-[-0.03em] text-fin-ink">ペルソナ選択</h2>
        <div className="text-sm text-fin-muted">
          該当: <span data-testid="match-count" className={`text-base font-bold tabular-nums text-fin-accent transition-opacity duration-200 ${countLoading ? 'opacity-50' : ''}`}>
            {countLoading && (
              <span className="mr-1 inline-block h-3 w-3 animate-spin rounded-full border-2 border-fin-accent/20 border-t-fin-accent align-middle" />
            )}
            {matchCount !== null ? matchCount.toLocaleString() : '—'}
          </span> 件
          <span className="ml-2 text-fin-muted/80">/ {filters.total_count.toLocaleString()} 総数</span>
        </div>
      </div>

      <div className="rounded-[1.75rem] border border-fin-border bg-fin-surface p-5 shadow-card">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-fin-muted">性別</label>
            <select
              value={sex}
              onChange={(e) => setSex(e.target.value)}
              className="w-full rounded-xl border border-fin-border bg-fin-panel px-3 py-2 text-sm text-fin-ink transition-colors focus:border-fin-accent focus:outline-none"
            >
              <option value="">すべて</option>
              {filters.sex.map((s) => (
                <option key={s} value={s}>{s === '男' ? '男性' : s === '女' ? '女性' : s}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-fin-muted">年齢 ({ageMin}〜{ageMax}歳)</label>
            <div className="flex gap-2">
              <input
                type="number"
                value={ageMin}
                min={18}
                max={ageMax}
                onChange={(e) => setAgeMin(Number.parseInt(e.target.value, 10) || 18)}
                className="w-full rounded-xl border border-fin-border bg-fin-panel px-3 py-2 text-sm text-fin-ink transition-colors focus:border-fin-accent focus:outline-none"
              />
              <span className="self-center text-fin-muted">〜</span>
              <input
                type="number"
                value={ageMax}
                min={ageMin}
                max={100}
                onChange={(e) => setAgeMax(Number.parseInt(e.target.value, 10) || 80)}
                className="w-full rounded-xl border border-fin-border bg-fin-panel px-3 py-2 text-sm text-fin-ink transition-colors focus:border-fin-accent focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-fin-muted">地域</label>
            <select
              value={region}
              onChange={(e) => { setRegion(e.target.value); setPrefecture('') }}
              className="w-full rounded-xl border border-fin-border bg-fin-panel px-3 py-2 text-sm text-fin-ink transition-colors focus:border-fin-accent focus:outline-none"
            >
              <option value="">すべての地域</option>
              {filters.regions.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-fin-muted">都道府県</label>
            <select
              value={prefecture}
              onChange={(e) => setPrefecture(e.target.value)}
              className="w-full rounded-xl border border-fin-border bg-fin-panel px-3 py-2 text-sm text-fin-ink transition-colors focus:border-fin-accent focus:outline-none"
            >
              <option value="">すべての都道府県</option>
              {filters.prefectures.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-fin-muted">職業</label>
            <input
              type="text"
              value={occupation}
              onChange={(e) => setOccupation(e.target.value)}
              placeholder="職業を入力..."
              list="occupation-list"
              className="w-full rounded-xl border border-fin-border bg-fin-panel px-3 py-2 text-sm text-fin-ink transition-colors placeholder:text-fin-muted focus:border-fin-accent focus:outline-none"
            />
            <datalist id="occupation-list">
              {filters.occupations_top50.map((o) => (
                <option key={o} value={o} />
              ))}
            </datalist>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-fin-muted">学歴</label>
            <select
              value={education}
              onChange={(e) => setEducation(e.target.value)}
              className="w-full rounded-xl border border-fin-border bg-fin-panel px-3 py-2 text-sm text-fin-ink transition-colors focus:border-fin-accent focus:outline-none"
            >
              <option value="">すべての学歴</option>
              {filters.education_levels.map((level) => (
                <option key={level} value={level}>{level}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-fin-muted">金融リテラシー</label>
            <select
              value={financialLiteracy}
              onChange={(e) => setFinancialLiteracy(e.target.value)}
              className="w-full rounded-xl border border-fin-border bg-fin-panel px-3 py-2 text-sm text-fin-ink transition-colors focus:border-fin-accent focus:outline-none"
            >
              <option value="">すべて</option>
              {filters.financial_literacy.map((level) => (
                <option key={level} value={level}>{level}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div>
        <div className="mb-2 text-xs font-medium text-fin-muted">サンプル数</div>
        <div className="flex flex-wrap gap-2">
          {COUNT_PRESETS.map((preset) => (
            <button
              key={preset.value}
              onClick={() => { setCount(preset.value); setCustomCount('') }}
              className={`rounded-full border px-4 py-2 text-sm font-medium transition-all duration-200
                ${count === preset.value && !customCount
                  ? 'border-fin-accent bg-fin-accent text-fin-surface'
                  : 'border-fin-border bg-fin-surface text-fin-ink hover:-translate-y-0.5 hover:border-fin-accent'
                }`}
            >
              {preset.label}
            </button>
          ))}
          <div className="flex items-center gap-2">
            <input
              type="number"
              value={customCount}
              onChange={(e) => setCustomCount(e.target.value)}
              placeholder="カスタム"
              min={1}
              max={200}
              className="w-24 rounded-full border border-fin-border bg-fin-surface px-3 py-2 text-sm text-fin-ink transition-colors placeholder:text-fin-muted focus:border-fin-accent focus:outline-none"
            />
          </div>
        </div>
      </div>

      <button
        onClick={handleSample}
        disabled={sampling}
        className="rounded-full bg-fin-accent px-6 py-3 text-sm font-semibold text-fin-surface transition-all duration-200 hover:-translate-y-0.5 hover:bg-fin-accentStrong disabled:opacity-50"
      >
        {sampling ? '抽出中...' : `ペルソナを抽出 (${resolvedCount}名)`}
      </button>

      {personas.length > 0 && (
        <div data-testid="persona-sampled-section">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm text-fin-muted">{personas.length}名 抽出済み</div>
            <button
              onClick={() => setStep(2)}
              className="rounded-full border border-fin-border bg-fin-surface px-5 py-2 text-sm font-semibold text-fin-ink transition-all duration-200 hover:-translate-y-0.5 hover:border-fin-accent hover:text-fin-accent"
            >
              次へ: 調査設定 →
            </button>
          </div>
          <PersonaCards personas={personas} />
        </div>
      )}
    </div>
  )
}
