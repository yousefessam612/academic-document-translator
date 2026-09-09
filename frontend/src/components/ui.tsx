export function Alert({
  kind,
  children,
}: {
  kind: 'error' | 'warning' | 'info' | 'success'
  children: React.ReactNode
}) {
  const styles = {
    error: 'bg-red-50 border-red-300 text-red-800',
    warning: 'bg-yellow-50 border-yellow-300 text-yellow-800',
    info: 'bg-blue-50 border-blue-300 text-blue-800',
    success: 'bg-emerald-50 border-emerald-300 text-emerald-800',
  }
  return (
    <div className={`border rounded-lg px-4 py-3 text-sm ${styles[kind]}`} role="alert">
      {children}
    </div>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-slate-500 text-sm">
      <div className="w-5 h-5 border-2 border-slate-300 border-t-emerald-500 rounded-full animate-spin" />
      {label}
    </div>
  )
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: string
  actions?: React.ReactNode
}) {
  return (
    <div className="flex items-start justify-between mb-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
        {description && <p className="text-slate-500 mt-1 text-sm">{description}</p>}
      </div>
      {actions}
    </div>
  )
}

export function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <div className={`bg-white rounded-xl border border-slate-200 shadow-sm ${className}`}>{children}</div>
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="text-center py-12 text-slate-400">
      <div className="text-lg font-medium">{title}</div>
      {hint && <div className="text-sm mt-1">{hint}</div>}
    </div>
  )
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

export function formatEta(seconds: number | null): string | null {
  if (seconds == null || !isFinite(seconds) || seconds <= 0) return null
  if (seconds < 60) return `~${Math.round(seconds)}s`
  if (seconds < 3600) return `~${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
  return `~${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}
