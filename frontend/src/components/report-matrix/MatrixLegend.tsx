interface MatrixLegendProps {
  industries: { name: string; color: string }[]
}

export default function MatrixLegend({ industries }: MatrixLegendProps) {
  return (
    <div className="flex flex-wrap gap-3 rounded-[1.5rem] border border-fin-border bg-fin-surface px-4 py-3">
      {industries.map((ind) => (
        <div key={ind.name} className="flex items-center gap-1.5">
          <div className="h-3 w-3 rounded-full" style={{ backgroundColor: ind.color }} />
          <span className="text-xs text-fin-muted">{ind.name}</span>
        </div>
      ))}
    </div>
  )
}
