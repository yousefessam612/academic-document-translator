const BASE = '/api'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init)
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = await response.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* ignore */
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  // ---- dashboard / health ----
  health: () => request<{ status: string; provider_configured: boolean }>('/health'),
  dashboard: () => request<import('../types').DashboardSummary>('/dashboard'),

  // ---- documents ----
  uploadDocument: async (file: File, onProgress?: (pct: number) => void): Promise<import('../types').Document> => {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', `${BASE}/documents/upload`)
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100))
      }
      xhr.onload = () => {
        try {
          const body = JSON.parse(xhr.responseText)
          if (xhr.status >= 200 && xhr.status < 300) resolve(body)
          else reject(new ApiError(xhr.status, body?.detail || 'Upload failed'))
        } catch {
          reject(new ApiError(xhr.status, 'Invalid server response'))
        }
      }
      xhr.onerror = () => reject(new ApiError(0, 'Network error during upload'))
      const form = new FormData()
      form.append('file', file)
      xhr.send(form)
    })
  },
  listDocuments: () => request<{ documents: import('../types').Document[]; total: number }>('/documents'),
  getDocument: (id: string) => request<import('../types').Document>(`/documents/${id}`),
  analyzeDocument: (id: string) =>
    request<{ message: string }>(`/documents/${id}/analyze`, { method: 'POST' }),
  getDocumentStructure: (id: string) =>
    request<{ total_blocks: number; blocks: unknown[] }>(`/documents/${id}/structure`),
  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: 'DELETE' }),
  downloadOriginalUrl: (id: string) => `${BASE}/documents/${id}/download/original`,
  downloadTranslatedUrl: (id: string) => `${BASE}/documents/${id}/download/translated`,

  // ---- translation jobs ----
  startTranslation: (documentId: string, settings: Partial<import('../types').JobSettings>) =>
    request<import('../types').Job>(`/translation/${documentId}/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ settings }),
    }),
  listJobs: (documentId?: string) =>
    request<{ jobs: import('../types').Job[]; total: number }>(
      `/translation/jobs${documentId ? `?document_id=${documentId}` : ''}`,
    ),
  getJob: (jobId: string) => request<import('../types').Job>(`/translation/jobs/${jobId}`),
  getJobChunks: (jobId: string, status?: string) =>
    request<{ total: number; completed: number; failed: number; chunks: import('../types').ChunkInfo[] }>(
      `/translation/jobs/${jobId}/chunks${status ? `?status=${status}` : ''}`,
    ),
  getProgress: (jobId: string) => request<import('../types').JobProgress>(`/translation/jobs/${jobId}/progress`),
  pauseJob: (jobId: string) => request<{ message: string }>(`/translation/jobs/${jobId}/pause`, { method: 'POST' }),
  resumeJob: (jobId: string) => request<import('../types').Job>(`/translation/jobs/${jobId}/resume`, { method: 'POST' }),
  cancelJob: (jobId: string) => request<{ message: string }>(`/translation/jobs/${jobId}/cancel`, { method: 'POST' }),
  retryFailed: (jobId: string) => request<import('../types').Job>(`/translation/jobs/${jobId}/retry-failed`, { method: 'POST' }),

  // ---- terminology ----
  listTerms: (search?: string, domain?: string) =>
    request<import('../types').Terminology[]>(
      `/terminology${search || domain ? `?${new URLSearchParams({ ...(search ? { search } : {}), ...(domain ? { domain } : {}) })}` : ''}`,
    ),
  terminologyMeta: () => request<{ domains: string[] }>('/terminology/meta'),
  createTerm: (payload: Partial<import('../types').Terminology>) =>
    request<import('../types').Terminology>('/terminology', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  updateTerm: (id: number, payload: Partial<import('../types').Terminology>) =>
    request<import('../types').Terminology>(`/terminology/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  deleteTerm: (id: number) => request<void>(`/terminology/${id}`, { method: 'DELETE' }),
  importTerms: async (file: File): Promise<{ imported: number; updated: number; skipped_duplicates: number; errors: string[] }> => {
    const form = new FormData()
    form.append('file', file)
    return request('/terminology/import', { method: 'POST', body: form })
  },
  exportTermsUrl: () => `${BASE}/terminology/export`,

  // ---- translation memory ----
  listMemory: (search?: string) =>
    request<import('../types').MemoryEntry[]>(`/memory${search ? `?search=${encodeURIComponent(search)}` : ''}`),
  memoryStats: () => request<{ total_entries: number }>('/memory/stats'),
  deleteMemoryEntry: (id: number) => request<void>(`/memory/${id}`, { method: 'DELETE' }),
  addMemoryEntry: (payload: { source_text: string; target_text: string; style?: string; domain?: string }) =>
    request<import('../types').MemoryEntry>('/memory', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  // ---- settings ----
  getSettings: () => request<import('../types').AppSettings>('/settings'),
  updateSettings: (payload: import('../types').AppSettings) =>
    request<import('../types').AppSettings>('/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  providerStatus: () => request<import('../types').ProviderStatus>('/settings/provider'),
  publicConfig: () => request<import('../types').PublicConfig>('/settings/config'),
}
