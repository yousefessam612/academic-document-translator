# Architecture Notes

## Translation pipeline

```
Upload (streamed, validated, sanitized)
   └─> DocumentAnalyzer
         ├─ PDF: PyMuPDF text-layer extraction (headings via font-size heuristics,
         │        tables via find_tables, bullets via marker regex)
         │        └─ scanned detection (avg chars/page + images) ─> OCRManager
         │             └─ TesseractEngine: page render (200 dpi) ─> text ─> paragraphs
         ├─ DOCX: python-docx body iteration (order preserved), heading styles,
         │        bold/italic runs -> ** / * markers, numPr lists, tables
         └─ TXT: encoding detection, markdown/caps heading heuristics, list detection
   └─> blocks: list[Block] (seq, type=heading|paragraph|list_item|table, level, page, rows)

SmartChunker
   ├─ pre-split oversized paragraphs at sentence boundaries
   ├─ chapter (H1) always starts a new chunk; headings attach to following content
   ├─ tables kept whole (row-group split only as last resort)
   └─ chunk metadata: chapter, section, page range, index, blocks, char/token estimate

TranslationEngine (per chunk)
   ├─ ContextManager: doc title, chapter/section, bounded prev/next text,
   │   previous translation tail, terminology matches, TM matches
   ├─ PromptBuilder (versioned): system rules + context sections + text to translate
   ├─ AgentRouterProvider: OpenAI-compatible /chat/completions
   │   ├─ retries: 429/5xx/network with exponential backoff + jitter
   │   ├─ fail fast: 401/403 (auth), 400 (invalid request), 402 (credits)
   │   └─ response validation: non-empty, no JSON corruption, no prompt echo,
   │       no "Translation:" prefixes, no code fences
   ├─ structural validation (retry with corrective message):
   │   length >= 25% of source, paragraph count preserved, table rows preserved,
   │   Arabic output for English source
   └─ per-chunk terminology consistency check -> ProcessingError (warnings)

JobManager (asyncio, in-process)
   ├─ statuses: queued analyzing extracting ocr chunking translating assembling
   │            completed failed paused cancelled
   ├─ bounded concurrency window (MAX_CONCURRENT_TRANSLATIONS)
   ├─ pause: cooperative (in-flight finish, then park on an asyncio.Event)
   ├─ resume: wakes the parked runner OR spawns a new one from persisted state
   ├─ cancel: cooperative stop
   ├─ every chunk state change committed immediately (SQLite WAL)
   └─ startup recovery: in-flight jobs -> paused ("Interrupted. You can resume.")

DocumentAssembler
   ├─ pre-validation: contiguous chunk indexes, all completed, non-empty translations,
   │   no duplicates -> refuse to generate otherwise
   └─ DOCX: RTL (w:bidi) paragraphs, complex-script fonts (w:rFonts/w:cs + szCs),
       Heading styles, List Bullet, rebuilt tables (bidiVisual), **bold**/*italic*
       markers -> real runs, justified body, right-aligned headings
```

## Key design decisions

- **Provider interface**: everything above the provider layer depends on
  `TranslationProvider`, never on AgentRouter specifics.
- **TM as context, not replacement**: matches (exact via SHA-256 of normalized
  source, fuzzy via SequenceMatcher >= 0.72 over recent entries) are injected
  into the prompt; the model keeps editorial control.
- **Honesty over fake success**: no chunk is ever marked completed without a
  validated translation; failures are surfaced per chunk with actionable
  messages; ETA is only displayed once statistically meaningful.
- **Original files are immutable**: uploads are only ever read; outputs go to
  `storage/outputs` under the job id.
