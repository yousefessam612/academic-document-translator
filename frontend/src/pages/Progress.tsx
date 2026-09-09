import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { ChunkInfo, Job, JobProgress } from '../types'
import { Alert, Card, Spinner, formatEta } from '../components/ui'
import ProgressBar from '../components/ProgressBar'
import StatusBadge from '../components/StatusBadge'

const POLL_MS = 1500

export default function Progress() {
  const { jobId } = useParams<{ jobId: string }>()
  const [job, setJob] = useState<Job | null>(null)
  const [progress, setProgress] = useState<JobProgress | null>(null)
  const [chunks, setChunks] = useState<ChunkInfo[]>([])
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [busy, setBusy] = useState(false)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!jobId) return
    let alive = true

    const poll = async () => {
      try {
        const [p, j] = await Promise.all([api.getProgress(jobId), api.getJob(jobId)])
        if (!alive) return
        setProgress(p)
        setJob(j)
        setError('')
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'Job not found')
      }
    }
    const loadChunks = async () => {
      try {
        const c = await api.getJobChunks(jobId)
        if (alive) setChunks(c.chunks)
      } catch {
        /* chunks optional */
      }
    }
    poll()
    loadChunks()
    timer.current = setInterval(() => {
      poll()
      loadChunks()
    }, POLL_MS)
    return () => {
      alive = false
      if (timer.current) clearInterval(timer.current)
    }
  }, [jobId])

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setActionError('')
    try {
      await fn()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  if (error && !progress) return <Alert kind="error">{error}</Alert>
  if (!progress || !job) return <Spinner label="Loading job…" />

  const isActive = ['queued', 'analyzing', 'extracting', 'ocr', 'chunking', 'translating', 'assembling'].includes(
    progress.status,
  )
  const eta = formatEta(progress.eta_seconds)
  const failedChunks = chunks.filter((c) => c.status === 'failed')
  const quality = job.quality_report

  return (
    <div>
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">
              <Link to={`/documents/${progress.document_id}`} className="hover:text-emerald-600">
                {progress.document_name || 'Document'}
              </Link>
            </h1>
            <StatusBadge status={progress.status} />
          </div>
          <p className="text-slate-500 text-sm mt-1">Job {progress.job_id.slice(0, 8)}…</p>
        </div>
        <div className="flex gap-2">
          {isActive && (
            <button
              disabled={busy}
              onClick={() => act(() => api.pauseJob(progress.job_id))}
              className="border border-amber-400 text-amber-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-amber-50 disabled:opacity-50"
            >
              Pause
            </button>
          )}
          {(progress.status === 'paused' || progress.status === 'failed') && (
            <button
              disabled={busy}
              onClick={() => act(() => api.resumeJob(progress.job_id))}
              className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50"
            >
              Resume
            </button>
          )}
          {progress.status === 'failed' && failedChunks.length > 0 && (
            <button
              disabled={busy}
              onClick={() => act(() => api.retryFailed(progress.job_id))}
              className="bg-amber-500 hover:bg-amber-600 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50"
            >
              Retry failed ({failedChunks.length})
            </button>
          )}
          {isActive && (
            <button
              disabled={busy}
              onClick={() => act(() => api.cancelJob(progress.job_id))}
              className="border border-red-300 text-red-600 px-4 py-2 rounded-lg text-sm font-medium hover:bg-red-50 disabled:opacity-50"
            >
              Cancel
            </button>
          )}
          {progress.status === 'completed' && (
            <a
              href={api.downloadTranslatedUrl(progress.document_id)}
              className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium"
            >
              Download Word document
            </a>
          )}
        </div>
      </div>

      {actionError && (
        <div className="mb-4">
          <Alert kind="error">{actionError}</Alert>
        </div>
      )}
      {progress.error_message && progress.status !== 'completed' && (
        <div className="mb-4">
          <Alert kind={progress.status === 'failed' ? 'error' : 'warning'}>{progress.error_message}</Alert>
        </div>
      )}
      {error && (
        <div className="mb-4">
          <Alert kind="error">Connection lost: {error}</Alert>
        </div>
      )}

      <Card className="p-6 mb-6">
        <div className="flex items-baseline justify-between mb-2">
          <h2 className="font-semibold">Translation progress</h2>
          <span className="text-2xl font-bold text-slate-900">{progress.progress_percentage.toFixed(1)}%</span>
        </div>
        <ProgressBar
          percentage={progress.progress_percentage}
          failed={progress.total_chunks ? (progress.failed_chunks / progress.total_chunks) * 100 : 0}
          className="h-4"
        />
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-5 text-sm">
          <div>
            <div className="text-xs text-slate-400">Chunks</div>
            <div className="font-medium">
              {progress.completed_chunks} / {progress.total_chunks || '?'} completed
              {progress.failed_chunks > 0 && (
                <span className="text-red-600"> · {progress.failed_chunks} failed</span>
              )}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-400">Current chapter</div>
            <div className="font-medium truncate">{progress.current_chapter || '—'}</div>
          </div>
          <div>
            <div className="text-xs text-slate-400">Current section</div>
            <div className="font-medium truncate">{progress.current_section || '—'}</div>
          </div>
          <div>
            <div className="text-xs text-slate-400">Estimated remaining</div>
            <div className="font-medium">{eta ?? 'calculating…'}</div>
          </div>
        </div>
      </Card>

      {progress.recent_errors.length > 0 && (
        <Card className="p-5 mb-6">
          <h2 className="font-semibold mb-3">Recent issues</h2>
          <ul className="space-y-2 text-sm">
            {progress.recent_errors.map((e, i) => (
              <li
                key={i}
                className={`rounded-lg px-3 py-2 ${
                  e.severity === 'warning' ? 'bg-yellow-50 text-yellow-800' : 'bg-red-50 text-red-800'
                }`}
              >
                {e.chunk_index != null && <strong>Chunk {e.chunk_index}: </strong>}
                {e.message}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {quality && progress.status === 'completed' && (
        <Card className="p-5 mb-6">
          <h2 className="font-semibold mb-3">Quality report</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mb-4">
            <div>
              <div className="text-xs text-slate-400">Chunks translated</div>
              <div className="font-medium">
                {quality.completed_chunks} / {quality.total_chunks}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Empty translations</div>
              <div className="font-medium">{quality.empty_translations}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Terms consistent</div>
              <div className="font-medium">{quality.terminology.consistent_terms}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Terms inconsistent</div>
              <div className="font-medium">
                {quality.terminology.inconsistent_terms.length}
              </div>
            </div>
          </div>
          {quality.terminology.inconsistent_terms.length > 0 && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-sm">
              <strong className="text-yellow-800">Terminology consistency warnings:</strong>
              <ul className="mt-2 space-y-1.5 text-yellow-800">
                {quality.terminology.inconsistent_terms.map((t) => (
                  <li key={t.english}>
                    <strong>{t.english}</strong> — preferred “{t.preferred}” but also found:{' '}
                    {Object.entries(t.used)
                      .filter(([k]) => k !== t.preferred)
                      .map(([variant, chunkIdxs]) => `“${variant}” (chunks ${chunkIdxs.join(', ')})`)
                      .join('; ')}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}

      <Card className="p-5">
        <h2 className="font-semibold mb-3">Chunks</h2>
        {chunks.length === 0 ? (
          <p className="text-sm text-slate-400">Chunks appear after analysis completes.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-400 border-b border-slate-100">
                  <th className="py-2 pr-3">#</th>
                  <th className="py-2 pr-3">Status</th>
                  <th className="py-2 pr-3">Chapter / Section</th>
                  <th className="py-2 pr-3">Pages</th>
                  <th className="py-2 pr-3">Chars</th>
                  <th className="py-2">Preview</th>
                </tr>
              </thead>
              <tbody>
                {chunks.map((c) => (
                  <tr key={c.chunk_index} className="border-b border-slate-50 align-top">
                    <td className="py-2 pr-3 text-slate-500">{c.chunk_index}</td>
                    <td className="py-2 pr-3">
                      <span
                        className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                          c.status === 'completed'
                            ? 'bg-emerald-100 text-emerald-700'
                            : c.status === 'failed'
                              ? 'bg-red-100 text-red-700'
                              : c.status === 'translating'
                                ? 'bg-amber-100 text-amber-700'
                                : 'bg-slate-100 text-slate-600'
                        }`}
                        title={c.error_message ?? undefined}
                      >
                        {c.status}
                      </span>
                    </td>
                    <td className="py-2 pr-3 text-slate-600 max-w-48 truncate">
                      {c.chapter || '—'}
                      {c.section ? ` / ${c.section}` : ''}
                    </td>
                    <td className="py-2 pr-3 text-slate-500">
                      {c.page_start > 0 ? `${c.page_start}–${c.page_end}` : '—'}
                    </td>
                    <td className="py-2 pr-3 text-slate-500">{c.char_count}</td>
                    <td className="py-2 text-slate-500 max-w-72">
                      <div className="truncate" title={c.source_preview}>
                        {c.source_preview || '—'}
                      </div>
                      {c.translation_preview && (
                        <div className="rtl truncate text-emerald-700" title={c.translation_preview}>
                          {c.translation_preview}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
