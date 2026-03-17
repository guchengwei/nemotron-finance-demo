import { useEffect, useState } from 'react'
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

  const [sampling, setSampling] = useState(false)
  const [matchCount, setMatchCount] = useState<number | null>(null)
  const [personas, setPersonas] = useState<Persona[]>([])

  // Load filters
  useEffect(() => {
    if (!filters) {
      api.getFilters().then((f) => {
        setFilters(f)
        setMatchCount(f.total_count)
      }).catch(console.error)
    } else {
      setMatchCount(filters.total_count)
    }
  }, [filters, setFilters])

  // Update match count when filters change
  useEffect(() => {
    const timeout = setTimeout(async () => {
      try {
        const result = await api.getSample({
          sex: sex || undefined,
          age_min: ageMin,
          age_max: ageMax,
          region: region || undefined,
          prefecture: prefecture || undefined,
          occupation: occupation || undefined,
          education: education || undefined,
          financial_literacy: financialLiteracy || undefined,
          count: 1,
        })
        setMatchCount(result.total_matching)
      } catch {
        // ignore
      }
    }, 300)
    return () => clearTimeout(timeout)
  }, [sex, ageMin, ageMax, region, prefecture, occupation, education, financialLiteracy])

  const handleSample = async () => {
    setSampling(true)
    try {
      const result = await api.getSample({
        sex: sex || undefined,
        age_min: ageMin,
        age_max: ageMax,
        region: region || undefined,
        prefecture: prefecture || undefined,
        occupation: occupation || undefined,
        education: education || undefined,
        financial_literacy: financialLiteracy || undefined,
        count,
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

  if (!filters) {
    return (
      <div className="flex items-center justify-center h-32">
        <div className="text-gray-500 text-sm">データベース読み込み中...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white">ペルソナ選択</h2>
        <div className="text-sm text-gray-400">
          該当: <span className="text-[#76B900] font-bold text-base">
            {matchCount !== null ? matchCount.toLocaleString() : '—'}
          </span> 件
          <span className="text-gray-600 ml-2">/ {filters.total_count.toLocaleString()} 総数</span>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-[#1c1c2e] border border-[rgba(118,185,0,0.1)] rounded-lg p-4">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {/* Sex */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">性別</label>
            <select
              value={sex}
              onChange={(e) => setSex(e.target.value)}
              className="w-full bg-[#141420] border border-[rgba(255,255,255,0.1)] rounded px-2 py-1.5 text-sm text-gray-200 focus:border-[#76B900] focus:outline-none"
            >
              <option value="">すべて</option>
              {filters.sex.map((s) => (
                <option key={s} value={s}>{s === '男' ? '男性' : s === '女' ? '女性' : s}</option>
              ))}
            </select>
          </div>

          {/* Age range */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">年齢 ({ageMin}〜{ageMax}歳)</label>
            <div className="flex gap-2">
              <input
                type="number"
                value={ageMin}
                min={18}
                max={ageMax}
                onChange={(e) => setAgeMin(parseInt(e.target.value) || 18)}
                className="w-full bg-[#141420] border border-[rgba(255,255,255,0.1)] rounded px-2 py-1.5 text-sm text-gray-200 focus:border-[#76B900] focus:outline-none"
              />
              <span className="text-gray-500 self-center">〜</span>
              <input
                type="number"
                value={ageMax}
                min={ageMin}
                max={100}
                onChange={(e) => setAgeMax(parseInt(e.target.value) || 80)}
                className="w-full bg-[#141420] border border-[rgba(255,255,255,0.1)] rounded px-2 py-1.5 text-sm text-gray-200 focus:border-[#76B900] focus:outline-none"
              />
            </div>
          </div>

          {/* Region */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">地域</label>
            <select
              value={region}
              onChange={(e) => { setRegion(e.target.value); setPrefecture('') }}
              className="w-full bg-[#141420] border border-[rgba(255,255,255,0.1)] rounded px-2 py-1.5 text-sm text-gray-200 focus:border-[#76B900] focus:outline-none"
            >
              <option value="">すべての地域</option>
              {filters.regions.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>

          {/* Prefecture */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">都道府県</label>
            <select
              value={prefecture}
              onChange={(e) => setPrefecture(e.target.value)}
              className="w-full bg-[#141420] border border-[rgba(255,255,255,0.1)] rounded px-2 py-1.5 text-sm text-gray-200 focus:border-[#76B900] focus:outline-none"
            >
              <option value="">すべての都道府県</option>
              {filters.prefectures.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>

          {/* Occupation */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">職業</label>
            <input
              type="text"
              value={occupation}
              onChange={(e) => setOccupation(e.target.value)}
              placeholder="職業を入力..."
              list="occupation-list"
              className="w-full bg-[#141420] border border-[rgba(255,255,255,0.1)] rounded px-2 py-1.5 text-sm text-gray-200 focus:border-[#76B900] focus:outline-none placeholder-gray-600"
            />
            <datalist id="occupation-list">
              {filters.occupations_top50.map((o) => (
                <option key={o} value={o} />
              ))}
            </datalist>
          </div>

          {/* Education */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">学歴</label>
            <select
              value={education}
              onChange={(e) => setEducation(e.target.value)}
              className="w-full bg-[#141420] border border-[rgba(255,255,255,0.1)] rounded px-2 py-1.5 text-sm text-gray-200 focus:border-[#76B900] focus:outline-none"
            >
              <option value="">すべての学歴</option>
              {filters.education_levels.map((e) => (
                <option key={e} value={e}>{e}</option>
              ))}
            </select>
          </div>

          {/* Financial literacy */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">金融リテラシー</label>
            <select
              value={financialLiteracy}
              onChange={(e) => setFinancialLiteracy(e.target.value)}
              className="w-full bg-[#141420] border border-[rgba(255,255,255,0.1)] rounded px-2 py-1.5 text-sm text-gray-200 focus:border-[#76B900] focus:outline-none"
            >
              <option value="">すべて</option>
              {filters.financial_literacy.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Count selector */}
      <div>
        <div className="text-xs text-gray-500 mb-2">サンプル数</div>
        <div className="flex flex-wrap gap-2">
          {COUNT_PRESETS.map((p) => (
            <button
              key={p.value}
              onClick={() => { setCount(p.value); setCustomCount('') }}
              className={`px-4 py-2 rounded text-sm font-medium transition-colors
                ${count === p.value && !customCount
                  ? 'bg-[#76B900] text-black'
                  : 'bg-[#1c1c2e] border border-[rgba(118,185,0,0.2)] text-gray-300 hover:border-[#76B900]'
                }`}
            >
              {p.label}
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
              className="w-24 bg-[#1c1c2e] border border-[rgba(118,185,0,0.2)] rounded px-3 py-2 text-sm text-gray-200 focus:border-[#76B900] focus:outline-none placeholder-gray-600"
            />
          </div>
        </div>
      </div>

      {/* Sample button */}
      <button
        onClick={handleSample}
        disabled={sampling}
        className="bg-[#76B900] hover:bg-[#8fd100] disabled:opacity-50 text-black font-bold px-6 py-2.5 rounded text-sm transition-colors"
      >
        {sampling ? '抽出中...' : `ペルソナを抽出 (${customCount || count}名)`}
      </button>

      {/* Persona cards */}
      {personas.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm text-gray-400">{personas.length}名 抽出済み</div>
            <button
              onClick={() => setStep(2)}
              className="bg-[#00A3E0] hover:bg-[#0090c5] text-white font-bold px-5 py-2 rounded text-sm transition-colors"
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
