import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { DashboardSummary } from '../types'
import { Card, PageHeader, Spinner, formatBytes } from '../components/ui'
import ProgressBar from '../components/ProgressBar'
import StatusBadge from '../components/StatusBadge'

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const data = await api.dashboard()
        if (alive) setSummary(data)
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'Failed to load dashboard')
      } finally {
        if (alive) setLoading(false)
      }
    }
    load()
    const timer = setInterval(load, 3000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])

  if (loading) return <Spinner label="Loading dashboard…" />
  if (error) return <div className="text-red-600 text-sm">{error}</div>
  if (!summary) return null

  const stats = [
    { label: 'Documents', value: summary.total_documents },
    { label: 'Completed translations', value: summary.completed_jobs },
    { label: 'Active jobs', value: summary.active_jobs },
    { label: 'Paused (resumable)', value: summary.paused_jobs },
    { label: 'Failed jobs', value: summary.failed_jobs },
    { label: 'Dictionary terms', value: summary.total_terms },
    { label: 'Memory entries', value: summary.total_memory_entries },
  ]

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Overview of documents, translations and dictionaries."
        actions={
          <Link
            to="/upload"
            className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium"
          >
            Upload document
          </Link>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-4 mb-8">
        {stats.map((s) => (
          <Card key={s.label} className="p-4">
            <div className="text-2xl font-bold text-slate-900">{s.value}</div>
            <div className="text-xs text-slate-500 mt-1">{s.label}</div>
          </Card>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <Card className="p-5">
          <h2 className="font-semibold mb-4">Recent translation jobs</h2>
          {summary.recent_jobs.length === 0 ? (
            <p className="text-sm text-slate-400">No translations yet. Upload a document to begin.</p>
          ) : (
            <ul className="space-y-3">
              {summary.recent_jobs.map((job) => (
                <li key={job.id} className="border border-slate-100 rounded-lg p-3">
                  <div className="flex items-center justify-between gap-2">
                    <Link to={`/progress/${job.id}`} className="text-sm font-medium text-slate-800 hover:text-emerald-600 truncate">
                      {job.document_name || 'Document'}
                    </Link>
                    <StatusBadge status={job.status} />
                  </div>
                  <div className="mt-2 flex items-center gap-3">
                    <ProgressBar
                      percentage={job.progress_percentage}
                      failed={job.total_chunks ? (job.failed_chunks / job.total_chunks) * 100 : 0}
                      className="flex-1"
                    />
                    <span className="text-xs text-slate-500 whitespace-nowrap">
                      {job.completed_chunks}/{job.total_chunks || '?'} chunks
                    </span>
                  </div>
                  <div className="mt-2 flex gap-2">
                    {(job.status === 'paused' || job.status === 'failed') && (
                      <Link
                        to={`/progress/${job.id}`}
                        className="text-xs bg-amber-100 text-amber-800 px-2 py-1 rounded hover:bg-amber-200"
                      >
                        Resume
                      </Link>
                    )}
                    {job.status === 'completed' && job.output_filename && (
                      <a
                        href={api.downloadTranslatedUrl(job.document_id)}
                        className="text-xs bg-emerald-100 text-emerald-800 px-2 py-1 rounded hover:bg-emerald-200"
                      >
                        Download DOCX
                      </a>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="p-5">
          <h2 className="font-semibold mb-4">Recent documents</h2>
          {summary.recent_documents.length === 0 ? (
            <p className="text-sm text-slate-400">No documents uploaded yet.</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {summary.recent_documents.map((doc) => (
                <li key={doc.id} className="py-2.5 flex items-center justify-between gap-2">
                  <Link to={`/documents/${doc.id}`} className="text-sm text-slate-800 hover:text-emerald-600 truncate">
                    {doc.filename}
                  </Link>
                  <span className="text-xs text-slate-400 whitespace-nowrap">
                    {doc.file_type.toUpperCase()} · {formatBytes(doc.file_size)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
