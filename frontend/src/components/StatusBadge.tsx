import type { JobStatus } from '../types'

const STATUS_STYLES: Record<string, string> = {
  queued: 'bg-slate-100 text-slate-700',
  analyzing: 'bg-blue-100 text-blue-700',
  extracting: 'bg-blue-100 text-blue-700',
  ocr: 'bg-purple-100 text-purple-700',
  chunking: 'bg-indigo-100 text-indigo-700',
  translating: 'bg-amber-100 text-amber-700',
  assembling: 'bg-cyan-100 text-cyan-700',
  completed: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-red-100 text-red-700',
  paused: 'bg-yellow-100 text-yellow-800',
  cancelled: 'bg-slate-200 text-slate-600',
}

export default function StatusBadge({ status }: { status: JobStatus | string }) {
  const cls = STATUS_STYLES[status] ?? 'bg-slate-100 text-slate-700'
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {status}
    </span>
  )
}
