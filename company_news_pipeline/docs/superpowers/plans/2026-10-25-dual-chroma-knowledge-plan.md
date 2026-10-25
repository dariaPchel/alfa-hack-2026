# Dual Chroma Knowledge Stores — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to implement this plan task-by-task.

**Goal:** Ingest Alpha Bank research and curated risk/decision methodology into physically separate local Chroma stores and expose narrowly scoped retrieval tools to their assigned AutoGen roles.

**Architecture:** Use the supplied `Аналитические материалы-20261025T170243Z-1-001.zip` as the initial Alpha corpus, then support future Drive sync. Use RouterAI-hosted multilingual embeddings and page-aware PDF extraction. Store source metadata, version/hash, page, license/scope, and excerpts with each vector. Bank Research Analyst and Impact Analyst/Action Analyst can search `alfa_research`; Risk Methodology Analyst and Impact Analyst/Action Analyst can search `risk_methodology`; Critic can verify cited IDs in either store. Agent roles have read/search access; ingestion worker owns writes.

**Tech Stack:** Chroma `PersistentClient`, PyMuPDF or pypdf, RouterAI `intfloat/multilingual-e5-large` embeddings, JSON source manifest.

**Spec:** `company_news_pipeline/docs/superpowers/specs/2026-10-25-anonymized-company-news-design.md`

## Interfaces

- `ingest_alfa_folder(source_dir: Path, manifest_path: Path) -> IngestionReport`
- `ingest_methodology_sources(registry_path: Path, source_dir: Path) -> IngestionReport`
- `retrieve_alfa(query: str, filters: dict | None = None, limit: int = 5) -> list[RetrievedChunk]`
- `retrieve_methodology(query: str, topic: str, limit: int = 5) -> list[RetrievedChunk]`
- `lookup_cited_chunks(store: Literal['alfa_research','risk_methodology'], chunk_ids: list[str]) -> list[RetrievedChunk]`

## Tasks

### Task 1: Add vector-store configuration and chunk contract

**Files:** Create `company_news_pipeline/news_analytics/knowledge/__init__.py`, `company_news_pipeline/news_analytics/knowledge/models.py`, `company_news_pipeline/news_analytics/knowledge/config.py`; modify `requirements.txt`.

- [ ] Define `RetrievedChunk` with `chunk_id`, `knowledge_store`, `document_id`, title, source URL, publication/version metadata, page range, section path, excerpt, and content hash.
- [ ] Configure separate persistent paths `data/vectorstores/alfa_research` and `data/vectorstores/risk_methodology`.
- [ ] Pin Chroma and PDF parser dependencies; call RouterAI embeddings with the same model ID and `passage:` / `query:` prefixes for ingestion and retrieval.
- [ ] Route embedding requests through the configured Wi-Fi-only RouterAI egress path; account for embedding tokens in the shared daily RouterAI budget and document that source excerpts are sent to the provider.
- [ ] Configure persistence so normal startup cannot reset or delete either collection.

**Completion check:** Both stores open independently, report separate counts, and a missing store is reported without silently recreating it empty after an ingestion error.

### Task 2: Create controlled source registry and local archive manifest

**Files:** Create `company_news_pipeline/news_analytics/knowledge/sources.json`, `company_news_pipeline/news_analytics/knowledge/drive_sync.py`.

- [ ] Register each of the nine PDFs in the supplied ZIP with archive name, extracted local path, SHA-256, retrieval date, and ingest status; retain the Drive folder URL for provenance/future refresh.
- [ ] Safely extract the supplied archive into a configurable local directory without overwriting unrelated files; record missing, duplicate, or unreadable entries.
- [ ] Keep optional Drive sync into that directory; use public Drive download when available and fall back to the supplied archive/local folder if the folder requires credentials.
- [ ] Compare hashes before reindexing; retain old manifest rows and mark replaced/removed docs inactive rather than silently erasing history.
- [ ] Do not log Drive credentials; request any needed access token from environment at runtime.

**Completion check:** A sync run identifies changed, unchanged, missing, and inaccessible documents separately.

### Task 3: Ingest Alpha research with page-level provenance

**Files:** Create `company_news_pipeline/news_analytics/knowledge/ingest_alfa.py`.

- [ ] Implement `ingest_alfa_folder(...)` for the local PDF folder and `alfa_research` store.
- [ ] Extract page text and headings; preserve page numbers; mark empty/scanned pages as OCR-required rather than indexing empty chunks.
- [ ] Chunk by section/page with overlap, retaining a title/date/page context in each chunk.
- [ ] Upsert using stable IDs derived from file hash, page, and chunk index; remove obsolete chunks for a superseded file hash only after replacement ingestion succeeds.
- [ ] Return per-file parse status, chunk count, page coverage, and OCR warnings.

**Completion check:** A retrieved Alpha excerpt can be traced to a specific Drive source URL and page.

### Task 4: Curate and ingest risk methodology

**Files:** Create `company_news_pipeline/news_analytics/knowledge/methodology_sources.json`, `company_news_pipeline/news_analytics/knowledge/ingest_methodology.py`.

- [ ] Register official ISO 31000 and COSO public pages, GOV.UK Orange/Green Books, NIST AI RMF/GenAI Profile, and Federal Reserve SR 26-2 with jurisdiction, applicability, version date, license, and allowed text source.
- [ ] Ingest only open/authorized source text; do not scrape/ingest full ISO/COSO copyrighted standards without a licensed copy.
- [ ] Exclude superseded Federal Reserve guidance from active retrieval while keeping source history; keep government and US banking documents marked as non-Russian normative context.
- [ ] Upsert page/section chunks into `risk_methodology`, separating corporate risk method, decision analysis, AI governance, and model governance topics.

**Completion check:** Retrieved method chunks include jurisdiction and scope labels that agents must preserve in their output.

### Task 5: Implement role-scoped retrieval and citation lookup

**Files:** Create `company_news_pipeline/news_analytics/knowledge/retrieval.py`, `company_news_pipeline/news_analytics/knowledge/tools.py`.

- [ ] Implement `retrieve_alfa(...)` and `retrieve_methodology(...)` against only their named store.
- [ ] Implement `lookup_cited_chunks(...)` as a read-only exact-ID lookup; reject broad query arguments to this tool.
- [ ] Expose broad read/search tools to Bank Research Analyst for `alfa_research`, Risk Methodology Analyst for `risk_methodology`, and both stores to Impact Analyst and Action Analyst; give Critic exact-ID read-only lookup in both.
- [ ] Keep raw Chroma clients private to the retrieval module; expose only assigned read/search tools to agents, with no collection access to Flask request handlers or browser JavaScript.
- [ ] Keep Chroma writes, deletes, and reindexing in the ingestion worker.
- [ ] Return `citation_not_found` when the cited chunk/page no longer exists.

**Completion check:** Each retrieval result is tagged with its store, source, version, page, and excerpt, and tool access matches the documented matrix.
