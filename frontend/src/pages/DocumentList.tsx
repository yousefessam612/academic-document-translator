import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { Document } from '../types'
import { Card, PageHeader, Spinner, EmptyState, formatBytes, Alert } from '../components/ui'
import StatusBadge from '../components/StatusBadge'

export default function DocumentList() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    api
      .listDocuments()
      .then((r) => setDocuments(r.documents))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load documents'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner label="Loading documents…" />

  return (
    <div>
      <PageHeader
        title="Documents"
        description="All uploaded documents. Originals are preserved untouched."
        actions={
          <Link to="/upload" className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium">
            Upload
          </Link>
        }
      />
      {error && <Alert kind="error">{error}</Alert>}
      {!error && documents.length === 0 && (
        <EmptyState title="No documents yet" hint="Upload a PDF, DOCX or TXT file to get started." />
      )}
      <div className="space-y-3">
        {documents.map((doc) => (
          <Card
            key={doc.id}
            className="p-4 hover:border-emerald-300 cursor-pointer"
          >
            <div onClick={() => navigate(`/documents/${doc.id}`)}>
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-medium text-slate-800 truncate">{doc.original_filename}</div>
                  <div className="text-xs text-slate-400 mt-0.5">
                    {doc.file_type.toUpperCase()} · {formatBytes(doc.file_size)}
                    {doc.analysis?.page_count ? ` · ${doc.analysis.page_count} pages` : ''}
                    {doc.requires_ocr ? ' · scanned (OCR)' : ''}
                    {doc.created_at ? ` · ${new Date(doc.created_at).toLocaleString()}` : ''}
                  </div>
                </div>
                <StatusBadge status={doc.status} />
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
