import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell
} from 'recharts'
import type { ReportResponse } from '../types'
import {
  formatAgeData, formatSexData, formatLiteracyData,
  formatScoreDistribution, CHART_COLORS
} from '../utils/chartHelpers'
import { scoreColor } from '../utils/scoreParser'

interface Props {
  report: ReportResponse
}

function MiniChart({ title, data, colorByScore = false }: {
  title: string
  data: { name: string; score?: number; count?: number }[]
  colorByScore?: boolean
}) {
  const dataKey = data[0]?.count !== undefined ? 'count' : 'score'
  return (
    <div className="rounded-[1.5rem] border border-fin-border bg-fin-surface p-4 shadow-card">
      <div className="mb-3 text-xs font-semibold tracking-[0.12em] text-fin-muted">{title}</div>
      <ResponsiveContainer width="100%" height={120}>
        <BarChart data={data} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
          <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#70685C' }} />
          <YAxis tick={{ fontSize: 10, fill: '#70685C' }} domain={dataKey === 'score' ? [0, 5] : undefined} />
          <Tooltip
            contentStyle={{ background: '#FBF8F2', border: '1px solid #D7CDBD', borderRadius: 16, boxShadow: '0 14px 32px rgba(31, 43, 42, 0.08)' }}
            labelStyle={{ color: '#70685C', fontSize: 11 }}
            itemStyle={{ color: '#1F6A5A', fontSize: 11 }}
          />
          <Bar dataKey={dataKey} radius={[3, 3, 0, 0]}>
            {data.map((entry, i) => (
              <Cell
                key={i}
                fill={colorByScore && entry.score
                  ? scoreColor(Math.round(entry.score))
                  : CHART_COLORS[i % CHART_COLORS.length]}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function DemographicCharts({ report }: Props) {
  const breakdown = report.demographic_breakdown
  const dist = report.score_distribution

  return (
    <div className="space-y-4">
      {/* Score distribution */}
      {dist && (
        <MiniChart
          title="評価分布"
          data={formatScoreDistribution(dist)}
          colorByScore={true}
        />
      )}

      {/* By demographic */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {breakdown?.by_age && Object.keys(breakdown.by_age).length > 0 && (
          <MiniChart title="年齢別平均" data={formatAgeData(breakdown.by_age)} />
        )}
        {breakdown?.by_sex && Object.keys(breakdown.by_sex).length > 0 && (
          <MiniChart title="性別平均" data={formatSexData(breakdown.by_sex)} />
        )}
        {breakdown?.by_financial_literacy && Object.keys(breakdown.by_financial_literacy).length > 0 && (
          <MiniChart title="金融リテラシー別" data={formatLiteracyData(breakdown.by_financial_literacy)} />
        )}
      </div>
    </div>
  )
}
