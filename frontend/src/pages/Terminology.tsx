import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Terminology } from '../types'
import { Alert, Card, PageHeader, Spinner, EmptyState } from '../components/ui'

export default function TerminologyPage() {
  const [terms, setTerms] = useState<Terminology[]>([])
  const [domains, setDomains] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [search, setSearch] = useState('')
  const [domain, setDomain] = useState('')
  const [editing, setEditing] = useState<Terminology | null>(null)
  const [creating, setCreating] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const emptyForm = {
    english_term: '',
    arabic_term: '',
    domain: 'General',
    definition: '',
    alternatives: '',
    notes: '',
    priority: 'preferred',
    active: true,
  }
  const [form, setForm] = useState(emptyForm)

  const load = async () => {
    try {
      const [t, meta] = await Promise.all([
        api.listTerms(search, domain),
        api.terminologyMeta(),
      ])
      setTerms(t)
      setDomains(meta.domains)
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load terminology')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const t = setTimeout(load, search ? 300 : 0)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, domain])

  const startCreate = () => {
    setCreating(true)
    setEditing(null)
    setForm(emptyForm)
  }
  const startEdit = (term: Terminology) => {
    setEditing(term)
    setCreating(false)
    setForm({
      english_term: term.english_term,
      arabic_term: term.arabic_term,
      domain: term.domain,
      definition: term.definition,
      alternatives: (term.alternatives || []).join('; '),
      notes: term.notes,
      priority: term.priority,
      active: term.active,
    })
  }
  const cancelForm = () => {
    setCreating(false)
    setEditing(null)
    setForm(emptyForm)
  }

  const save = async () => {
    setNotice('')
    const payload = {
      english_term: form.english_term.trim(),
      arabic_term: form.arabic_term.trim(),
      domain: form.domain.trim() || 'General',
      definition: form.definition,
      alternatives: form.alternatives
        .split(';')
        .map((s) => s.trim())
        .filter(Boolean),
      notes: form.notes,
      priority: form.priority,
      active: form.active,
    }
    if (!payload.english_term || !payload.arabic_term) {
      setError('English and Arabic terms are both required.')
      return
    }
    try {
      if (editing) await api.updateTerm(editing.id, payload)
      else await api.createTerm(payload)
      cancelForm()
      await load()
      setNotice(editing ? 'Term updated.' : 'Term added.')
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save term')
    }
  }

  const remove = async (term: Terminology) => {
    if (!confirm(`Delete "${term.english_term}"?`)) return
    try {
      await api.deleteTerm(term.id)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete term')
    }
  }

  const importCsv = async (file: File) => {
    setNotice('')
    try {
      const result = await api.importTerms(file)
      await load()
      setNotice(
        `Imported ${result.imported} terms, skipped ${result.skipped_duplicates} duplicates.` +
          (result.errors.length ? ` Errors: ${result.errors.slice(0, 3).join(' ')}` : ''),
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import failed')
    }
  }

  return (
    <div>
      <PageHeader
        title="Terminology dictionary"
        description="Academic terms enforced during translation for consistent Arabic terminology."
        actions={
          <div className="flex gap-2">
            <a
              href={api.exportTermsUrl()}
              className="border border-slate-300 text-slate-600 px-3 py-2 rounded-lg text-sm hover:bg-slate-50"
            >
              Export CSV
            </a>
            <button
              onClick={() => fileRef.current?.click()}
              className="border border-slate-300 text-slate-600 px-3 py-2 rounded-lg text-sm hover:bg-slate-50"
            >
              Import CSV
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) void importCsv(f)
                e.target.value = ''
              }}
            />
            <button
              onClick={startCreate}
              className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium"
            >
              Add term
            </button>
          </div>
        }
      />

      {error && (
        <div className="mb-4">
          <Alert kind="error">{error}</Alert>
        </div>
      )}
      {notice && (
        <div className="mb-4">
          <Alert kind="success">{notice}</Alert>
        </div>
      )}

      {(creating || editing) && (
        <Card className="p-5 mb-6">
          <h2 className="font-semibold mb-4">{editing ? `Edit: ${editing.english_term}` : 'New term'}</h2>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">English term *</label>
              <input
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                value={form.english_term}
                onChange={(e) => setForm((f) => ({ ...f, english_term: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Arabic translation *</label>
              <input
                dir="rtl"
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                value={form.arabic_term}
                onChange={(e) => setForm((f) => ({ ...f, arabic_term: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Domain</label>
              <input
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                value={form.domain}
                onChange={(e) => setForm((f) => ({ ...f, domain: e.target.value }))}
                list="domain-list"
              />
              <datalist id="domain-list">
                {domains.map((d) => (
                  <option key={d} value={d} />
                ))}
              </datalist>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Priority</label>
              <select
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                value={form.priority}
                onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value }))}
              >
                <option value="preferred">Preferred</option>
                <option value="allowed">Allowed</option>
                <option value="avoid">Avoid</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Alternatives (separate with ;)
              </label>
              <input
                dir="rtl"
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                value={form.alternatives}
                onChange={(e) => setForm((f) => ({ ...f, alternatives: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Definition</label>
              <input
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                value={form.definition}
                onChange={(e) => setForm((f) => ({ ...f, definition: e.target.value }))}
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-slate-700 mb-1">Notes</label>
              <input
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                value={form.notes}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={form.active}
                onChange={(e) => setForm((f) => ({ ...f, active: e.target.checked }))}
                className="rounded border-slate-300 text-emerald-600"
              />
              Active
            </label>
          </div>
          <div className="mt-5 flex gap-2">
            <button
              onClick={save}
              className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium"
            >
              {editing ? 'Save changes' : 'Add term'}
            </button>
            <button
              onClick={cancelForm}
              className="border border-slate-300 text-slate-600 px-4 py-2 rounded-lg text-sm"
            >
              Cancel
            </button>
          </div>
        </Card>
      )}

      <div className="flex gap-3 mb-4">
        <input
          placeholder="Search terms…"
          className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-sm"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="border border-slate-300 rounded-lg px-3 py-2 text-sm"
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
        >
          <option value="">All domains</option>
          {domains.map((d) => (
            <option key={d}>{d}</option>
          ))}
        </select>
      </div>

      {loading ? (
        <Spinner label="Loading dictionary…" />
      ) : terms.length === 0 ? (
        <EmptyState title="No terms found" hint="Add terms or import a CSV file." />
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-400 border-b border-slate-100">
                <th className="px-4 py-3">English</th>
                <th className="px-4 py-3">Arabic</th>
                <th className="px-4 py-3">Domain</th>
                <th className="px-4 py-3">Priority</th>
                <th className="px-4 py-3">Active</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {terms.map((term) => (
                <tr key={term.id} className="border-b border-slate-50 hover:bg-slate-50">
                  <td className="px-4 py-2.5 font-medium text-slate-800">{term.english_term}</td>
                  <td className="px-4 py-2.5 rtl text-slate-800">{term.arabic_term}</td>
                  <td className="px-4 py-2.5 text-slate-500">{term.domain}</td>
                  <td className="px-4 py-2.5">
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs ${
                        term.priority === 'preferred'
                          ? 'bg-emerald-100 text-emerald-700'
                          : 'bg-slate-100 text-slate-600'
                      }`}
                    >
                      {term.priority}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">{term.active ? '✓' : '—'}</td>
                  <td className="px-4 py-2.5 text-right whitespace-nowrap">
                    <button onClick={() => startEdit(term)} className="text-slate-500 hover:text-emerald-600 px-2">
                      Edit
                    </button>
                    <button onClick={() => remove(term)} className="text-slate-500 hover:text-red-600 px-2">
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}
