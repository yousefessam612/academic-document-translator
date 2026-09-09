export default function ProgressBar({
  percentage,
  failed = 0,
  className = '',
}: {
  percentage: number
  failed?: number
  className?: string
}) {
  const pct = Math.max(0, Math.min(100, percentage))
  const failedPct = Math.min(failed, 100 - pct)
  return (
    <div className={`h-3 w-full bg-slate-200 rounded-full overflow-hidden flex ${className}`}>
      <div
        className="h-full bg-emerald-500 transition-all duration-500"
        style={{ width: `${pct}%` }}
        data-testid="progress-fill"
      />
      {failedPct > 0 && (
        <div className="h-full bg-red-400" style={{ width: `${failedPct}%` }} title={`${failed} failed`} />
      )}
    </div>
  )
}
