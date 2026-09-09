import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { MemoryEntry } from '../types'
import { Alert, Card, EmptyState, PageHeader, Spinner } from '../components/ui'

export default function MemoryPage() {
  const [entries, setEntries] = useState<MemoryEntry[]>([])
  const [stats, setStats] = useState<{ total_entries: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [source, setSource] = useState('')
  const [target, setTarget] = useState('')
  const [saving, setSaving] = useState(false)

  const load = async () => {
    try {
      const [e, s] = await Promise.all([api.listMemory(search), api.memoryStats()])
      setEntries(e)
      setStats(s)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load memory')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const t = setTimeout(load, search ? 300 : 0)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  const add = async () => {
    if (!source.trim() || !target.trim()) return
    setSaving(true)
    try {
      await api.addMemoryEntry({ source_text: source, target_text: target })
      setSource('')
      setTarget('')
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add entry')
    } finally {
      setSaving(false)
    }
  }

  const remove = async (id: number) => {
    try {
      await api.deleteMemoryEntry(id)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete entry')
    }
  }

  return (
    <div>
      <PageHeader
        title="Translation memory"
        description="Approved source/translation pairs reused for consistent phrasing (suggested to the model, never blindly inserted)."
      />

      {error && (
        <div className="mb-4">
          <Alert kind="error">{error}</Alert>
        </div>
      )}

      <Card className="p-5 mb-6">
        <h2 className="font-semibold mb-4">Add entry manually</h2>
        <div className="grid md:grid-cols-2 gap-4">
          <textarea
            placeholder="English source segment…"
            className="border border-slate-300 rounded-lg px-3 py-2 text-sm h-24"
            value={source}
            onChange={(e) => setSource(e.target.value)}
          />
          <textarea
            dir="rtl"
            placeholder="الترجمة المعتمدة…"
            className="border border-slate-300 rounded-lg px-3 py-2 text-sm h-24"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          />
        </div>
        <button
          onClick={add}
          disabled={saving || !source.trim() || !target.trim()}
          className="mt-3 bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-300 text-white px-4 py-2 rounded-lg text-sm font-medium"
        >
          {saving ? 'Saving…' : 'Add to memory'}
        </button>
      </Card>

      <div className="flex items-center justify-between mb-4">
        <input
          placeholder="Search memory…"
          className="flex-1 mr-4 border border-slate-300 rounded-lg px-3 py-2 text-sm"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <span className="text-sm text-slate-500 whitespace-nowrap">
          {stats ? `${stats.total_entries.toLocaleString()} entries` : ''}
        </span>
      </div>

      {loading ? (
        <Spinner label="Loading memory…" />
      ) : entries.length === 0 ? (
        <EmptyState title="Translation memory is empty" hint="Entries are added automatically as chunks are translated." />
      ) : (
        <div className="space-y-3">
          {entries.map((entry) => (
            <Card key={entry.id} className="p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-slate-700 line-clamp-2">{entry.source_text}</div>
                  <div className="rtl text-sm text-emerald-700 mt-1 line-clamp-2">{entry.target_text}</div>
                  <div className="text-xs text-slate-400 mt-2">
                    {entry.style} · {entry.domain} · used {entry.use_count}×
                    {entry.created_at ? ` · ${new Date(entry.created_at).toLocaleDateString()}` : ''}
                  </div>
                </div>
                <button
                  onClick={() => remove(entry.id)}
                  className="text-slate-400 hover:text-red-600 text-sm"
                  title="Delete entry"
                >
                  ✕
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
