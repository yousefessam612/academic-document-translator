import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Document, Job, JobSettings } from '../types'
import { Alert, Card, PageHeader, Spinner, formatBytes } from '../components/ui'
import StatusBadge from '../components/StatusBadge'

const STYLES = ['Academic', 'Scientific', 'Educational', 'Technical', 'General']
const DOMAINS = [
  'Visual Impairment',
  'Special Education',
  'Education',
  'Psychology',
  'Assistive Technology',
  'General',
]

export default function DocumentDetails() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [doc, setDoc] = useState<Document | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [starting, setStarting] = useState(false)
  const [settings, setSettings] = useState<JobSettings>({
    source_language: 'English',
    target_language: 'Arabic',
    style: 'Academic',
    domain: 'General',
    use_global_dictionary: true,
    use_domain_dictionary: true,
    use_custom_dictionary: true,
    use_translation_memory: true,
    chunk_target_chars: null,
    retranslate_completed: false,
    use_ocr_if_needed: true,
  })

  useEffect(() => {
    if (!id) return
    let alive = true
    const load = async () => {
      try {
        const d = await api.getDocument(id)
        if (!alive) return
        setDoc(d)
        if (d.analysis?.is_scanned) {
          setSettings((s) => ({ ...s, use_ocr_if_needed: true }))
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'Document not found')
      } finally {
        if (alive) setLoading(false)
      }
    }
    load()
    const timer = setInterval(load, 4000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [id])

  const analysis = doc?.analysis
  const analyzed = doc?.status === 'analyzed' && !!analysis
  const analyzing = ['uploaded', 'analyzing', 'extracting', 'ocr'].includes(doc?.status ?? '')
  const analysisFailed = doc?.status === 'analysis_failed'

  const retryAnalysis = async () => {
    if (!id) return
    setError('')
    try {
      await api.analyzeDocument(id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start analysis')
    }
  }

  const estimatedUsage = useMemo(() => {
    if (!analysis) return null
    const chars = analysis.character_count
    const inputTokens = Math.round(chars / 4)
    return {
      chunks: analysis.estimated_chunks,
      inputTokens,
      outputTokens: inputTokens,
      totalTokens: inputTokens * 2,
    }
  }, [analysis])

  const startTranslation = async () => {
    if (!id) return
    setStarting(true)
    setError('')
    try {
      const job: Job = await api.startTranslation(id, settings)
      navigate(`/progress/${job.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start translation')
    } finally {
      setStarting(false)
    }
  }

  if (loading) return <Spinner label="Loading document…" />
  if (!doc) return <Alert kind="error">{error || 'Document not found.'}</Alert>

  return (
    <div>
      <PageHeader
        title={doc.original_filename}
        description={`${doc.file_type.toUpperCase()} · ${formatBytes(doc.file_size)}`}
        actions={
          <div className="flex items-center gap-3">
            <StatusBadge status={doc.status} />
            <a
              href={api.downloadOriginalUrl(doc.id)}
              className="text-sm text-slate-500 hover:text-slate-700 border border-slate-300 px-3 py-1.5 rounded-lg"
            >
              Original
            </a>
          </div>
        }
      />

      {doc.status === 'uploaded' && (
        <Alert kind="info">The document is queued for analysis…</Alert>
      )}
      {['analyzing', 'extracting'].includes(doc.status) && (
        <Alert kind="info">Analyzing document… (extraction and structure detection)</Alert>
      )}
      {doc.status === 'ocr' && (
        <Alert kind="info">
          The PDF appears to be scanned. Running local OCR
          {analysis?.ocr_progress ? ` — page ${analysis.ocr_progress}` : ''}. This can take a
          while for large scanned books.
        </Alert>
      )}
      {analysisFailed && (
        <div className="space-y-3">
          <Alert kind="error">
            {analysis?.error || 'Document analysis failed.'}
          </Alert>
          <button
            onClick={retryAnalysis}
            className="bg-amber-500 hover:bg-amber-600 text-white px-4 py-2 rounded-lg text-sm font-medium"
          >
            Retry analysis
          </button>
        </div>
      )}
      {error && <Alert kind="error">{error}</Alert>}

      {analyzed && analysis && (
        <div className="space-y-6">
          <Card className="p-5">
            <h2 className="font-semibold mb-4">Analysis</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <Stat label="Type" value={analysis.file_type.toUpperCase()} />
              <Stat label="Size" value={formatBytes(analysis.file_size)} />
              <Stat label="Pages" value={analysis.page_count != null ? String(analysis.page_count) : '—'} />
              <Stat
                label="Text"
                value={analysis.ocr_used ? 'OCR (scanned)' : analysis.has_extractable_text ? 'Detected' : 'None'}
              />
              <Stat label="Characters" value={analysis.character_count.toLocaleString()} />
              <Stat label="Headings" value={String(analysis.heading_count)} />
              <Stat label="Paragraphs" value={String(analysis.paragraph_count)} />
              <Stat label="Tables" value={String(analysis.table_count)} />
              <Stat label="List items" value={String(analysis.list_item_count)} />
              <Stat label="Est. translation units" value={analysis.estimated_translation_units.toLocaleString()} />
              <Stat label="Est. chunks" value={String(analysis.estimated_chunks)} />
              <Stat label="Domain hint" value={analysis.is_scanned ? 'Scanned PDF' : 'Text-based'} />
            </div>
            {analysis.chapters?.length > 0 && (
              <div className="mt-4">
                <div className="text-xs font-medium text-slate-500 mb-1">Detected chapters</div>
                <div className="text-sm text-slate-700 line-clamp-2">
                  {analysis.chapters.slice(0, 6).join(' · ')}
                  {analysis.chapters.length > 6 ? ` (+${analysis.chapters.length - 6} more)` : ''}
                </div>
              </div>
            )}
            {doc.title && (
              <div className="mt-4">
                <div className="text-xs font-medium text-slate-500 mb-1">Detected title</div>
                <div className="text-sm text-slate-700">{doc.title}</div>
              </div>
            )}
          </Card>

          <Card className="p-5">
            <h2 className="font-semibold mb-4">Translation settings</h2>
            <div className="grid md:grid-cols-2 gap-5">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Source language</label>
                <select
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-slate-50"
                  value={settings.source_language}
                  disabled
                >
                  <option>English</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Target language</label>
                <select
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-slate-50"
                  value={settings.target_language}
                  disabled
                >
                  <option>Arabic</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Translation style</label>
                <select
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                  value={settings.style}
                  onChange={(e) => setSettings((s) => ({ ...s, style: e.target.value }))}
                >
                  {STYLES.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Domain</label>
                <select
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                  value={settings.domain}
                  onChange={(e) => setSettings((s) => ({ ...s, domain: e.target.value }))}
                >
                  {DOMAINS.map((d) => (
                    <option key={d}>{d}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Chunk target size (characters, optional)
                </label>
                <input
                  type="number"
                  min={500}
                  max={12000}
                  step={500}
                  placeholder="Server default (4000)"
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                  value={settings.chunk_target_chars ?? ''}
                  onChange={(e) =>
                    setSettings((s) => ({
                      ...s,
                      chunk_target_chars: e.target.value ? Number(e.target.value) : null,
                    }))
                  }
                />
              </div>
              <div className="space-y-2 pt-1">
                <Check
                  label="Global terminology dictionary"
                  checked={settings.use_global_dictionary}
                  onChange={(v) => setSettings((s) => ({ ...s, use_global_dictionary: v }))}
                />
                <Check
                  label={`Domain dictionary (${settings.domain})`}
                  checked={settings.use_domain_dictionary}
                  onChange={(v) => setSettings((s) => ({ ...s, use_domain_dictionary: v }))}
                />
                <Check
                  label="Custom dictionary entries"
                  checked={settings.use_custom_dictionary}
                  onChange={(v) => setSettings((s) => ({ ...s, use_custom_dictionary: v }))}
                />
                <Check
                  label="Use translation memory"
                  checked={settings.use_translation_memory}
                  onChange={(v) => setSettings((s) => ({ ...s, use_translation_memory: v }))}
                />
                <Check
                  label="Use OCR if the PDF is scanned"
                  checked={settings.use_ocr_if_needed}
                  onChange={(v) => setSettings((s) => ({ ...s, use_ocr_if_needed: v }))}
                />
              </div>
            </div>

            {estimatedUsage && (
              <div className="mt-5 bg-slate-50 border border-slate-200 rounded-lg p-4 text-sm text-slate-600">
                <strong className="text-slate-700">Estimated usage:</strong>{' '}
                {estimatedUsage.chunks} chunks · ~
                {estimatedUsage.totalTokens.toLocaleString()} tokens total (~
                {estimatedUsage.inputTokens.toLocaleString()} in + ~
                {estimatedUsage.outputTokens.toLocaleString()} out). Translation consumes your
                AgentRouter credits.
              </div>
            )}

            <div className="mt-6 flex items-center gap-3">
              <button
                onClick={startTranslation}
                disabled={starting}
                className="bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-300 text-white px-5 py-2.5 rounded-lg text-sm font-medium"
              >
                {starting ? 'Starting…' : 'Start translation'}
              </button>
              <Link to="/terminology" className="text-sm text-slate-500 hover:text-slate-700">
                Manage terminology →
              </Link>
            </div>
          </Card>
        </div>
      )}

      {analyzing && !analysisFailed && !error && (
        <div className="mt-6">
          <Spinner label="Analyzing document…" />
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-slate-400">{label}</div>
      <div className="font-medium text-slate-800">{value}</div>
    </div>
  )
}

function Check({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-slate-700">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
      />
      {label}
    </label>
  )
}
