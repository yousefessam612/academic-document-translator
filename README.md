---
title: Academic Document Translator
emoji: 🌐
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# Academic Document Translator

A production-ready web application that translates large academic, scientific, educational, and technical documents from **English to Arabic** using an **AgentRouter-compatible LLM API**, producing a fully formatted, right-to-left Arabic Microsoft Word (.docx) document.

Designed for academic books and research materials: it preserves document structure (chapters, sections, headings, lists, tables, bold/italic), enforces a terminology dictionary, reuses a translation memory, and can resume interrupted translations without re-translating completed chunks.

---

## What it does

1. Upload a document (PDF / DOCX / TXT, up to **100 MB** per file, streamed upload).
2. Automatic analysis: file type, page count, character count, headings, paragraphs, tables, lists, chapter boundaries, and whether the PDF is **scanned**.
3. Scanned PDFs are processed with **local OCR** (Tesseract) — the original file is never sent to the LLM.
4. **Smart chunking**: splits by chapter → section → subsection → paragraph → sentence boundaries. Headings are never separated from their content, tables are kept whole, sentences are never cut mid-way.
5. Each chunk is translated with bounded context (document/chapter/section titles, neighboring text, terminology dictionary, translation-memory matches) through a versioned academic translation prompt.
6. Terminology consistency is checked per chunk and across the whole document; a quality report is generated.
7. Translations run as **background jobs** with pause / resume / cancel, automatic retries with exponential backoff, configurable concurrency, and per-chunk persistence — a crash or restart never loses completed work.
8. The final Arabic **DOCX** is assembled with right-to-left paragraphs, Arabic complex-script fonts, headings, lists, tables, and bold/italic runs — ready to download.

---

## Architecture

```
academic-translator/
├── backend/                     Python · FastAPI · SQLAlchemy · SQLite
│   ├── app/
│   │   ├── api/                 REST routes (documents, translation, terminology, memory, settings, dashboard)
│   │   ├── core/                config (.env), structured logging, security/filename sanitization
│   │   ├── db/                  engine/session + init
│   │   ├── models/              Document, TranslationJob, TranslationChunk, Terminology,
│   │   │                        TranslationMemoryEntry, AppSettings, ProcessingError
│   │   ├── schemas/             Pydantic request/response models
│   │   ├── services/
│   │   │   ├── document/        PDF/DOCX/TXT extraction + structure + analyzer (scanned detection)
│   │   │   ├── ocr/             modular OCR engines (Tesseract, local)
│   │   │   ├── translation/     SmartChunker, ContextManager, PromptBuilder,
│   │   │   │                    TranslationProvider interface, AgentRouterProvider, engine, consistency
│   │   │   ├── terminology/     dictionary service + CSV import/export + seed terms, translation memory
│   │   │   ├── jobs/            JobManager (async background jobs, pause/resume/cancel)
│   │   │   └── export/          DocumentAssembler (Arabic RTL DOCX generation + validation)
│   │   ├── utils/               streaming file storage, temp cleanup, text/token utilities
│   │   └── main.py              FastAPI app (also serves the built frontend)
│   ├── tests/                   102 automated tests (mocked provider — no real API calls)
│   └── requirements.txt
├── frontend/                    React 19 · TypeScript · Vite · Tailwind CSS 4
│   └── src/pages/               Dashboard, Upload, Documents, Document Details,
│                                Progress, Terminology, Translation Memory, Completed, Settings
├── scripts/                     mock AgentRouter server, E2E/interruption tests, test PDF generator
├── storage/                     uploads/ processed/ outputs/ temp/  (gitignored)
├── .env.example
└── README.md
```

**Provider isolation:** the application only talks to the `TranslationProvider` interface (`translate()`, `validate_connection()`, `health_check()`, `get_model()`, `estimate_usage()`). `AgentRouterProvider` implements it over the OpenAI-compatible chat-completions API. Adding another provider later requires no changes elsewhere.

**Privacy:** documents are stored locally. Only the text of the chunk being translated (plus bounded context) is sent to the API — never the whole file.

---

## Requirements

- **Python 3.10+** (built and tested on Python 3.14, Windows)
- **Node.js 18+** (built and tested on Node 24, Windows)
- **Tesseract OCR** — *optional*, only needed for scanned PDFs
  - Windows installer: <https://github.com/UB-Mannheim/tesseract/wiki>
  - Or: `winget install --id UB-Mannheim.TesseractOCR`
  - If not on PATH, set `TESSERACT_CMD` in `.env` (see below)

---

## Installation (Windows)

Open **PowerShell** in the project root:

```powershell
cd C:\academic-translator

# 1. Backend virtual environment + dependencies
cd backend
python -m venv .venv
.\.venv\Scripts\pip.exe install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt
cd ..

# 2. Frontend dependencies
cd frontend
npm install
cd ..

# 3. Configure environment
copy .env.example .env
notepad .env
```

### Environment variables (`.env`)

| Variable | Required | Description |
|---|---|---|
| `AGENTROUTER_API_KEY` | **Yes** | Your AgentRouter API key. Never committed to git. |
| `AGENTROUTER_BASE_URL` | Yes | Default `https://agentrouter.org/v1` (OpenAI-compatible endpoint). |
| `AGENTROUTER_MODEL` | **Yes** | Model name to use (see your AgentRouter model list; e.g. `glm-5.3`, `deepseek-v4-flash`). |
| `AGENTROUTER_CLIENT_UA` | No | Client User-Agent. AgentRouter's WAF rejects generic HTTP clients; the default Codex CLI wire image is verified to work. |
| `AGENTROUTER_ORIGINATOR` | No | Client originator header (part of the accepted wire image). |
| `AGENTROUTER_MAX_TOKENS` | No | Completion token cap per chunk. Default `16384`. **Escalates automatically (x2 per retry)** when a reasoning model exhausts it. |
| `AGENTROUTER_REASONING_EFFORT` | No | `low` (default, recommended for translation), `medium`, `high`, or empty to omit. `low` prevents reasoning models from burning the token budget and returning empty content. |
| `MAX_FILE_SIZE_MB` | No | Upload limit per file (default `100`). |
| `MAX_CONCURRENT_TRANSLATIONS` | No | Parallel chunk translations (default `2`). |
| `MAX_RETRIES` | No | Retry attempts per chunk on temporary API failures (default `3`). |
| `RETRY_BASE_DELAY_SECONDS` | No | Exponential backoff base (default `2`). |
| `CHUNK_TARGET_CHARS` / `CHUNK_MAX_CHARS` | No | Chunk sizing (default `4000` / `6000`). |
| `CONTEXT_CHARS` | No | Context window sent with each chunk (default `1500`). |
| `REQUEST_TIMEOUT_SECONDS` | No | LLM request timeout (default `180`). |
| `TESSERACT_CMD` | No | Full path to `tesseract.exe` if not on PATH. |
| `TEMP_CLEANUP_HOURS` | No | Abandoned temp-file cleanup age (default `24`). |

The app **fails gracefully** with a clear message if the key/model are missing — it never crashes and never exposes the key to the browser.

### AgentRouter notes (learned from live testing)

- **WAF**: `agentrouter.org` rejects generic HTTP clients with `unauthorized client detected`. The provider sends the Codex CLI client headers by default (configurable via `AGENTROUTER_CLIENT_UA` / `AGENTROUTER_ORIGINATOR`).
- **Reasoning models** (`glm-5.3`): the model thinks in `reasoning_content` before emitting `content`. With a low `max_tokens`, reasoning can exhaust the budget and return **empty content**. The provider handles this: `reasoning_effort=low` by default, token-cap escalation on retry, and explicit rejection of `finish_reason=length` responses.
- **Table fidelity**: table rows are sent with `[1] [2] [3]` row markers; validation verifies every marker comes back exactly once with the same cell count, so the model can never merge or drop rows silently.

---

## Running

### Backend (terminal 1)

```powershell
cd C:\academic-translator\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend (terminal 2 — development)

```powershell
cd C:\academic-translator\frontend
npm run dev
```

Open **http://localhost:5173** (the dev server proxies `/api` to the backend).

### Production single-server mode

```powershell
cd C:\academic-translator\frontend
npm run build          # outputs to frontend/dist
cd ..\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The backend automatically serves the built frontend at **http://127.0.0.1:8000**.

---

## Using the application

1. **Upload** — drag & drop or pick a PDF/DOCX/TXT file (≤ 100 MB). Analysis runs automatically.
2. **Document Details** — review the analysis (pages, text detection, estimated chunks/units), pick translation **style** (Academic / Scientific / Educational / Technical / General) and **domain** (Visual Impairment, Special Education, Education, Psychology, Assistive Technology, General), enable dictionaries/translation memory/OCR, and see the **estimated token usage** before starting.
3. **Start translation** — a background job runs: analyzing → extracting → (ocr) → chunking → translating → assembling → completed. Progress shows real percentages, current chapter/section, chunk counts, failed chunks, and an ETA only when reliably calculable.
4. **Pause / Resume / Cancel / Retry failed** — completed chunks are never re-translated on resume (persisted per chunk in the database).
5. **Completed** — download the generated Arabic Word document. Terminology consistency findings appear in the job's quality report.

### Terminology dictionary

- Manage terms (English, Arabic, domain, definition, alternatives, notes, priority, active) on the **Terminology** page.
- Import CSV with headers `English,Arabic,Domain` (optionally `Definition`, `Alternatives` separated by `;`). Duplicates are skipped and reported; invalid rows are listed.
- Export the whole dictionary as CSV.
- During translation, matching terms are injected into every prompt and must be used; consistency is verified afterwards.

### Translation memory

- Approved source/translation pairs are stored automatically as chunks complete (deduplicated).
- Exact and fuzzy matches (local similarity search; upgradeable to embeddings) are provided to the model as context for consistent phrasing — never blindly inserted.

---

## Supported file types & limits

| Type | Support |
|---|---|
| PDF | Text-based (PyMuPDF structure extraction: headings, paragraphs, tables, lists) and **scanned** (via local Tesseract OCR) |
| DOCX | Full structure: heading styles, paragraphs, bold/italic, lists, tables |
| TXT | Paragraph/heading/list heuristics |
| EPUB / PPTX | Architecture supports adding them later; rejected with a clear message today |

- **100 MB limit per file**, enforced during streaming upload (99 MB → accepted, 100 MB → accepted, 100 MB + 1 byte → rejected with a clear error).
- Filenames are sanitized; path traversal is blocked; file content is verified against its claimed type (magic bytes).

## OCR

Scanned-PDF detection samples pages for extractable text. When a PDF has (almost) no text layer, the pipeline renders pages → OCR (Tesseract, local) → text → structure detection → chunking → translation. If Tesseract is not installed, the job fails with instructions instead of silently producing an empty document.

---

## Testing

### Automated tests (no real API calls — the provider is mocked)

```powershell
cd C:\academic-translator\backend
.\.venv\Scripts\python.exe -m pytest tests -v
```

Covers: file validation, the 100 MB boundary, PDF/DOCX/TXT extraction, scanned-PDF detection, OCR (runs when Tesseract is installed), smart chunking, terminology CRUD + CSV import/export, translation memory, provider error mapping + retries (auth / rate limit / 5xx / malformed responses), prompt building, translation validation, consistency checking, job resume without re-translation, pause/resume/cancel, missing-chunk assembly guards, DOCX generation, and Arabic RTL formatting.

### End-to-end tests against a running app

```powershell
# 1. Start the local mock AgentRouter server (OpenAI-compatible, zero credits)
.\backend\.venv\Scripts\python.exe scripts\mock_agentrouter.py          # add "0.8" for a slow mode

# 2. Point .env at it: AGENTROUTER_BASE_URL=http://127.0.0.1:8787/v1 ,
#    AGENTROUTER_API_KEY=mock-test-key, AGENTROUTER_MODEL=mock-model

# 3. Start the backend, then:
.\backend\.venv\Scripts\python.exe scripts\make_test_pdf.py storage\temp\test_book.pdf
.\backend\.venv\Scripts\python.exe scripts\e2e_test.py                  # full workflow
.\backend\.venv\Scripts\python.exe scripts\interrupt_test.py            # kill backend mid-job + resume
.\backend\.venv\Scripts\python.exe scripts\nokey_test.py                # missing-key failure path
```

### Large-document real-API test (verified)

```powershell
# Generates a 25-page, 11,800+ word academic book and translates it fully
# through the real AgentRouter API.
.\backend\.venv\Scripts\python.exe scripts\make_big_test_pdf.py storage\temp\big_test_book.pdf
.\backend\.venv\Scripts\python.exe scripts\big_real_test.py
```

Verified result with `glm-5.3`: 30/30 chunks, 0 failures, ~12,000 Arabic words
translated in under 4 minutes, 99%+ content coverage in the final DOCX, all
dictionary terms applied, full RTL formatting.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `AGENTROUTER_API_KEY is missing` on job start | Fill `AGENTROUTER_API_KEY` and `AGENTROUTER_MODEL` in `.env`, then resume the job. |
| `unauthorized client detected` (401) | The WAF rejected the client fingerprint — check `AGENTROUTER_CLIENT_UA` / `AGENTROUTER_ORIGINATOR` (defaults are verified working). |
| `Response content is empty` retries | Normal for reasoning models under token pressure; the provider escalates the cap automatically. If it persists, set `AGENTROUTER_REASONING_EFFORT=low` or switch to a non-reasoning model (e.g. `deepseek-v4-flash`). |
| `Translation service authentication failed` | The key is wrong/expired — check it in `.env`. |
| `The PDF appears to be scanned... Tesseract OCR is not installed` | Install Tesseract (see Requirements) and set `TESSERACT_CMD` if needed. |
| `Some chunks are incomplete. The final Word document cannot yet be generated.` | A job has pending/failed chunks — open its Progress page and click **Resume** / **Retry failed**. |
| `Chunk N failed after 3 attempts` | Temporary API/network issue — resume the job; only failed chunks are retried. |
| `File exceeds the 100 MB limit` | Split the document or raise `MAX_FILE_SIZE_MB`. |
| Job stuck as `paused` after restarting the app | Expected: interrupted jobs are parked on startup. Click **Resume**. |
| Frontend can't reach the API | Ensure the backend runs on port 8000; the Vite dev server proxies `/api`. |
| Rate-limit (429) errors | Lower `MAX_CONCURRENT_TRANSLATIONS` or increase `RETRY_BASE_DELAY_SECONDS`. |
| Document stays `uploaded` (analysis never runs) | Analysis runs automatically after upload; if it shows `analysis_failed`, the error reason is displayed with a Retry button. |

---

## Security notes

- The API key lives **only** in the backend `.env` (gitignored); it is never sent to the browser or logged.
- Uploads are stored under random internal IDs; client filenames are sanitized and never used as paths.
- File type is verified by content signature, not just extension; request size is limited.
- Stack traces are never returned to end users unless `DEBUG=true`.
- Original uploaded files are never modified or deleted automatically; temporary files older than `TEMP_CLEANUP_HOURS` are cleaned periodically.
- Logs are structured (job/document/chunk ids, operations, durations) and never contain API keys or full document content.

## Known limitations

- Translation runs inside the API process (asyncio) — suitable for a single user/workstation; a external worker queue would be needed for multi-instance deployments.
- Translation-memory fuzzy search scans recent entries locally (exact matches are hashed); designed to be upgraded to embeddings/vector search.
- PDF table extraction depends on detectable table structures (ruled tables work best); the synthetic PDFs without ruling lines may extract as plain paragraphs.
- EPUB and PPTX are not yet implemented (architecture is ready for them).
