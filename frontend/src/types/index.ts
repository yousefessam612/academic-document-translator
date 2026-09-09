export interface DocumentAnalysis {
  file_type: string
  file_size: number
  page_count: number | null
  has_extractable_text: boolean
  is_scanned: boolean
  ocr_used: boolean
  character_count: number
  heading_count: number
  paragraph_count: number
  table_count: number
  list_item_count: number
  estimated_translation_units: number
  estimated_chunks: number
  chapters: string[]
  title?: string
  /** Set while OCR is running (e.g. "5/30") */
  ocr_progress?: string
  /** Set when analysis failed */
  error?: string
}

export interface Document {
  id: string
  original_filename: string
  file_type: string
  file_size: number
  status: string
  title: string
  requires_ocr: boolean
  created_at: string | null
  analysis: DocumentAnalysis | null
}

export type JobStatus =
  | 'queued'
  | 'analyzing'
  | 'extracting'
  | 'ocr'
  | 'chunking'
  | 'translating'
  | 'assembling'
  | 'completed'
  | 'failed'
  | 'paused'
  | 'cancelled'

export interface JobSettings {
  source_language: string
  target_language: string
  style: string
  domain: string
  use_global_dictionary: boolean
  use_domain_dictionary: boolean
  use_custom_dictionary: boolean
  use_translation_memory: boolean
  chunk_target_chars: number | null
  retranslate_completed: boolean
  use_ocr_if_needed: boolean
}

export interface Job {
  id: string
  document_id: string
  status: JobStatus
  total_chunks: number
  completed_chunks: number
  failed_chunks: number
  current_chunk_index: number
  progress_percentage: number
  settings: Record<string, unknown>
  quality_report: QualityReport | null
  output_filename: string | null
  started_at: string | null
  updated_at: string | null
  completed_at: string | null
  error_message: string | null
  document_name: string | null
}

export interface QualityReport {
  total_chunks: number
  completed_chunks: number
  failed_chunks: number
  empty_translations: number
  missing_indexes: number[]
  duplicate_indexes: number[]
  terminology: {
    terms_checked: number
    chunks_checked: number
    consistent_terms: number
    inconsistent_terms: InconsistentTerm[]
  }
}

export interface InconsistentTerm {
  english: string
  preferred: string
  used: Record<string, number[]>
  chunks_without_preferred: number[]
}

export interface JobProgress {
  job_id: string
  document_id: string
  document_name: string | null
  status: JobStatus
  total_chunks: number
  completed_chunks: number
  failed_chunks: number
  current_chunk_index: number
  current_chapter: string | null
  current_section: string | null
  progress_percentage: number
  eta_seconds: number | null
  error_message: string | null
  recent_errors: { chunk_index: number | null; type: string; severity: string; message: string }[]
  consistency_issues: InconsistentTerm[]
}

export interface Terminology {
  id: number
  english_term: string
  arabic_term: string
  domain: string
  definition: string
  alternatives: string[]
  notes: string
  priority: string
  active: boolean
}

export interface MemoryEntry {
  id: number
  source_text: string
  target_text: string
  target_language: string
  style: string
  domain: string
  use_count: number
  created_at: string | null
}

export interface AppSettings {
  source_language: string
  target_language: string
  style: string
  domain: string
  chunk_target_chars: number
  use_global_dictionary: boolean
  use_domain_dictionary: boolean
  use_custom_dictionary: boolean
  use_translation_memory: boolean
}

export interface DashboardSummary {
  total_documents: number
  total_jobs: number
  completed_jobs: number
  active_jobs: number
  failed_jobs: number
  paused_jobs: number
  total_terms: number
  total_memory_entries: number
  recent_documents: {
    id: string
    filename: string
    file_type: string
    file_size: number
    status: string
    created_at: string | null
  }[]
  recent_jobs: {
    id: string
    document_id: string
    document_name: string | null
    status: JobStatus
    progress_percentage: number
    total_chunks: number
    completed_chunks: number
    failed_chunks: number
    updated_at: string | null
    error_message: string | null
    output_filename: string | null
  }[]
}

export interface ProviderStatus {
  configured: boolean
  model: string | null
  base_url: string | null
  connected: boolean | null
  detail: string | null
}

export interface PublicConfig {
  max_file_size_mb: number
  max_concurrent_translations: number
  max_retries: number
  chunk_target_chars: number
  supported_types: string[]
  ocr_engines: { name: string; available: boolean }[]
}

export interface ChunkInfo {
  chunk_index: number
  status: string
  chapter: string
  section: string
  page_start: number
  page_end: number
  char_count: number
  attempts: number
  error_message: string | null
  source_preview: string
  translation_preview: string
}
