import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Job } from '../types'
import { Alert, Card, EmptyState, PageHeader, Spinner } from '../components/ui'

export default function CompletedDocuments() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .listJobs()
      .then((r) => setJobs(r.jobs.filter((j) => j.status === 'completed')))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <PageHeader
        title="Completed documents"
        description="Download the generated Arabic Word documents."
      />
      {error && <Alert kind="error">{error}</Alert>}
      {loading ? (
        <Spinner label="Loading…" />
      ) : jobs.length === 0 ? (
        <EmptyState title="No completed translations yet" hint="Finished translations will appear here." />
      ) : (
        <div className="space-y-3">
          {jobs.map((job) => (
            <Card key={job.id} className="p-5">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <Link
                    to={`/progress/${job.id}`}
                    className="font-medium text-slate-800 hover:text-emerald-600"
                  >
                    {job.document_name || 'Document'}
                  </Link>
                  <div className="text-xs text-slate-400 mt-1">
                    {job.completed_chunks} chunks · {job.quality_report?.terminology.consistent_terms ?? 0} consistent terms
                    {job.completed_at ? ` · ${new Date(job.completed_at).toLocaleString()}` : ''}
                  </div>
                </div>
                <a
                  href={api.downloadTranslatedUrl(job.document_id)}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap"
                >
                  Download DOCX
                </a>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
