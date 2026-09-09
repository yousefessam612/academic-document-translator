import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { AppSettings, ProviderStatus, PublicConfig } from '../types'
import { Alert, Card, PageHeader, Spinner } from '../components/ui'

const STYLES = ['Academic', 'Scientific', 'Educational', 'Technical', 'General']
const DOMAINS = [
  'Visual Impairment',
  'Special Education',
  'Education',
  'Psychology',
  'Assistive Technology',
  'General',
]

export default function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [provider, setProvider] = useState<ProviderStatus | null>(null)
  const [config, setConfig] = useState<PublicConfig | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    Promise.all([api.getSettings(), api.publicConfig()])
      .then(([s, c]) => {
        setSettings(s)
        setConfig(c)
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load settings'))
  }, [])

  const checkProvider = async () => {
    setChecking(true)
    try {
      setProvider(await api.providerStatus())
    } finally {
      setChecking(false)
    }
  }

  const save = async () => {
    if (!settings) return
    setSaving(true)
    setSaved(false)
    try {
      const s = await api.updateSettings(settings)
      setSettings(s)
      setSaved(true)
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  if (error && !settings) return <Alert kind="error">{error}</Alert>
  if (!settings) return <Spinner label="Loading settings…" />

  return (
    <div>
      <PageHeader title="Settings" description="Default translation settings and provider status." />

      {error && (
        <div className="mb-4">
          <Alert kind="error">{error}</Alert>
        </div>
      )}
      {saved && (
        <div className="mb-4">
          <Alert kind="success">Settings saved.</Alert>
        </div>
      )}

      <div className="grid lg:grid-cols-2 gap-6">
        <Card className="p-5">
          <h2 className="font-semibold mb-4">Default translation settings</h2>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Source language</label>
                <select className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-slate-50" disabled>
                  <option>English</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Target language</label>
                <select className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-slate-50" disabled>
                  <option>Arabic</option>
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Default style</label>
                <select
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                  value={settings.style}
                  onChange={(e) => setSettings((s) => (s ? { ...s, style: e.target.value } : s))}
                >
                  {STYLES.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Default domain</label>
                <select
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                  value={settings.domain}
                  onChange={(e) => setSettings((s) => (s ? { ...s, domain: e.target.value } : s))}
                >
                  {DOMAINS.map((d) => (
                    <option key={d}>{d}</option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Chunk target size (characters)
              </label>
              <input
                type="number"
                min={500}
                max={12000}
                step={500}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                value={settings.chunk_target_chars}
                onChange={(e) =>
                  setSettings((s) => (s ? { ...s, chunk_target_chars: Number(e.target.value) } : s))
                }
              />
            </div>
            <div className="space-y-2">
              <Check
                label="Global dictionary"
                checked={settings.use_global_dictionary}
                onChange={(v) => setSettings((s) => (s ? { ...s, use_global_dictionary: v } : s))}
              />
              <Check
                label="Domain dictionary"
                checked={settings.use_domain_dictionary}
                onChange={(v) => setSettings((s) => (s ? { ...s, use_domain_dictionary: v } : s))}
              />
              <Check
                label="Custom dictionary"
                checked={settings.use_custom_dictionary}
                onChange={(v) => setSettings((s) => (s ? { ...s, use_custom_dictionary: v } : s))}
              />
              <Check
                label="Translation memory"
                checked={settings.use_translation_memory}
                onChange={(v) => setSettings((s) => (s ? { ...s, use_translation_memory: v } : s))}
              />
            </div>
            <button
              onClick={save}
              disabled={saving}
              className="bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-300 text-white px-4 py-2 rounded-lg text-sm font-medium"
            >
              {saving ? 'Saving…' : 'Save settings'}
            </button>
          </div>
        </Card>

        <div className="space-y-6">
          <Card className="p-5">
            <h2 className="font-semibold mb-4">Translation provider (AgentRouter)</h2>
            <p className="text-sm text-slate-500 mb-4">
              The API key is stored only in the server's <code>.env</code> file — it is never sent
              to the browser.
            </p>
            {provider ? (
              <div
                className={`rounded-lg p-4 text-sm ${
                  provider.configured && provider.connected
                    ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                    : 'bg-yellow-50 text-yellow-800 border border-yellow-200'
                }`}
              >
                <div className="font-medium mb-1">
                  {provider.configured
                    ? provider.connected
                      ? 'Connected'
                      : 'Configured but not reachable'
                    : 'Not configured'}
                </div>
                {provider.model && <div>Model: {provider.model}</div>}
                {provider.base_url && <div>Endpoint: {provider.base_url}</div>}
                {provider.detail && <div className="mt-1">{provider.detail}</div>}
              </div>
            ) : (
              <button
                onClick={checkProvider}
                disabled={checking}
                className="border border-slate-300 text-slate-600 px-4 py-2 rounded-lg text-sm hover:bg-slate-50"
              >
                {checking ? 'Checking…' : 'Check provider connection'}
              </button>
            )}
            {provider && (
              <button
                onClick={checkProvider}
                disabled={checking}
                className="mt-3 border border-slate-300 text-slate-600 px-4 py-2 rounded-lg text-sm hover:bg-slate-50"
              >
                {checking ? 'Checking…' : 'Re-check'}
              </button>
            )}
          </Card>

          {config && (
            <Card className="p-5">
              <h2 className="font-semibold mb-4">Server configuration</h2>
              <dl className="text-sm space-y-2">
                <Row label="Max file size" value={`${config.max_file_size_mb} MB`} />
                <Row label="Parallel translations" value={String(config.max_concurrent_translations)} />
                <Row label="Retries per chunk" value={String(config.max_retries)} />
                <Row
                  label="OCR engines"
                  value={config.ocr_engines
                    .map((e) => `${e.name}: ${e.available ? 'available' : 'not installed'}`)
                    .join(', ')}
                />
                <Row label="Supported types" value={config.supported_types.join(', ')} />
              </dl>
              <p className="text-xs text-slate-400 mt-4">
                These values come from the server's .env configuration.
              </p>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-slate-800 font-medium text-right">{value}</dd>
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
