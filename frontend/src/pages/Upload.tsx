import { useCallback, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { Document, PublicConfig } from '../types'
import { Alert, Card, PageHeader, formatBytes } from '../components/ui'
import { useEffect } from 'react'

const ACCEPT = '.pdf,.docx,.txt'

export default function Upload() {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState<File | null>(null)
  const [progress, setProgress] = useState(0)
  const [uploaded, setUploaded] = useState<Document | null>(null)
  const [error, setError] = useState('')
  const [config, setConfig] = useState<PublicConfig | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.publicConfig().then(setConfig).catch(() => {})
  }, [])

  const doUpload = useCallback(
    async (file: File) => {
      setError('')
      setUploaded(null)
      setUploading(file)
      setProgress(0)
      try {
        const doc = await api.uploadDocument(file, setProgress)
        setUploaded(doc)
      } catch (e) {
        if (e instanceof ApiError) setError(e.message)
        else setError('Upload failed. Is the backend running?')
      } finally {
        setUploading(null)
        setProgress(0)
      }
    },
    [],
  )

  const handleFiles = useCallback(
    (files: FileList | null) => {
      const file = files?.[0]
      if (!file) return
      const limitMb = config?.max_file_size_mb ?? 100
      if (file.size > limitMb * 1024 * 1024) {
        setError(`File exceeds the ${limitMb} MB limit (${formatBytes(file.size)}).`)
        return
      }
      const ext = file.name.toLowerCase().split('.').pop() ?? ''
      if (!['pdf', 'docx', 'txt'].includes(ext)) {
        setError(`Unsupported file type ".${ext}". Supported: PDF, DOCX, TXT.`)
        return
      }
      void doUpload(file)
    },
    [config, doUpload],
  )

  return (
    <div>
      <PageHeader
        title="Upload document"
        description={`PDF, DOCX or TXT · up to ${config?.max_file_size_mb ?? 100} MB per file · analysis runs automatically`}
      />

      {error && (
        <div className="mb-4">
          <Alert kind="error">{error}</Alert>
        </div>
      )}

      {uploaded && (
        <div className="mb-6">
          <Alert kind="success">
            <div className="flex items-center justify-between gap-4">
              <span>
                <strong>{uploaded.original_filename}</strong> uploaded and being analyzed.
              </span>
              <Link
                to={`/documents/${uploaded.id}`}
                className="bg-emerald-600 text-white px-3 py-1.5 rounded text-xs font-medium whitespace-nowrap"
              >
                Open document →
              </Link>
            </div>
          </Alert>
        </div>
      )}

      <Card
        className={`p-10 border-2 border-dashed transition-colors ${
          dragging ? 'border-emerald-500 bg-emerald-50' : 'border-slate-300'
        }`}
      >
        <div
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            handleFiles(e.dataTransfer.files)
          }}
          className="text-center"
        >
          <div className="text-5xl mb-4">📄</div>
          <p className="text-slate-700 font-medium">Drag &amp; drop your document here</p>
          <p className="text-slate-400 text-sm mt-1">or</p>
          <button
            onClick={() => inputRef.current?.click()}
            className="mt-3 bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2.5 rounded-lg text-sm font-medium"
            disabled={!!uploading}
          >
            {uploading ? 'Uploading…' : 'Choose file'}
          </button>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => handleFiles(e.target.files)}
          />
          <p className="text-xs text-slate-400 mt-4">
            Supported: PDF (including scanned, via local OCR), DOCX, TXT
          </p>
        </div>
      </Card>

      {uploading && (
        <div className="mt-4">
          <div className="flex justify-between text-sm text-slate-600 mb-1">
            <span className="truncate">{uploading.name}</span>
            <span>{progress}%</span>
          </div>
          <div className="h-2.5 bg-slate-200 rounded-full overflow-hidden">
            <div className="h-full bg-emerald-500 transition-all" style={{ width: `${progress}%` }} />
          </div>
          <p className="text-xs text-slate-400 mt-1">{formatBytes(uploading.size)}</p>
        </div>
      )}

      {config && (
        <div className="mt-8 grid sm:grid-cols-3 gap-4 text-sm">
          <Card className="p-4">
            <div className="font-medium text-slate-700">Size limit</div>
            <div className="text-slate-500 mt-1">{config.max_file_size_mb} MB per file</div>
          </Card>
          <Card className="p-4">
            <div className="font-medium text-slate-700">OCR</div>
            <div className="text-slate-500 mt-1">
              {config.ocr_engines.some((e) => e.available)
                ? `Local OCR available (${config.ocr_engines.find((e) => e.available)?.name})`
                : 'Tesseract not installed — scanned PDFs cannot be processed'}
            </div>
          </Card>
          <Card className="p-4">
            <div className="font-medium text-slate-700">Concurrency</div>
            <div className="text-slate-500 mt-1">
              {config.max_concurrent_translations} parallel translations · {config.max_retries} retries
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}
