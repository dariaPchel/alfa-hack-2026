# Knowledge stores

Two independent persistent Chroma stores are used:

- `data/vectorstores/alfa_research` for the nine supplied Alpha research PDFs.
- `data/vectorstores/risk_methodology` for public/authorized risk and decision-method excerpts.

Set `NEWS_ANALYTICS_CHROMA_ALFA_RESEARCH` or `NEWS_ANALYTICS_CHROMA_RISK_METHODOLOGY` to relocate either store. Normal retrieval opens an existing store and requires its collection metadata to contain `ingestion_ready=true`. Only an ingestion command may create a collection; successful nonempty ingestion writes the marker. A failed/empty indexing run therefore cannot turn a missing store into a seemingly healthy empty one. Docker deployments can use Chroma HTTP services by setting `NEWS_ANALYTICS_CHROMA_ALFA_RESEARCH_HOST` and `NEWS_ANALYTICS_CHROMA_RISK_METHODOLOGY_HOST` (plus optional per-store ports); local development uses separate `PersistentClient` directories.

Embeddings use RouterAI's OpenAI-compatible `POST /api/v1/embeddings` endpoint and `intfloat/multilingual-e5-large` (1024 dimensions). The same RouterAI API key and Wi-Fi-only egress path as chat inference are required. Inputs use the E5 `passage:` / `query:` prefixes; chunks are kept below the model's 512-token context. Alpha PDF excerpts and methodology notes are sent to RouterAI's embedding provider for vectorization. Embedding spend is recorded against the shared 500 RUB/day RouterAI budget at the configured per-million-token rate. Chroma stores record the model name and vector size and refuse retrieval with a mismatched model; reindex old stores before switching.

The supplied archive is extracted to `data/alfa_research`. `sources.json` records each archive member, stable document ID, source folder, retrieval date, and SHA-256. The ingestion command is `python -m news_analytics.knowledge.ingest_alfa`; it reports OCR-required pages and does not index empty pages. User supplied PDF files are ignored by Git; manifests and code remain tracked.

Methodology source metadata is in `company_news_pipeline/news_analytics/knowledge/methodology_sources.json`. The tracked `.md` files in `company_news_pipeline/data/methodology_sources` are concise, analyst-authored summaries with source links and scope limits; they are not full copies of the standards. Full ISO/COSO standards are excluded unless a licensed local copy is supplied. Government/banking sources retain jurisdiction and scope on every chunk. Ingestion uses these local summaries and reports genuinely missing files as `source_text_missing`; it never silently fetches or substitutes source text.

## Role access

| Role | `alfa_research` | `risk_methodology` |
|---|---|---|
| Bank Research Analyst | Search/read | — |
| Risk Methodology Analyst | — | Search/read |
| Impact Analyst | Search/read | Search/read |
| Action Analyst | Search/read | Search/read |
| Critic / Source Checker | Exact chunk-ID lookup | Exact chunk-ID lookup |
| Ingestion worker | Write/reindex | Write/reindex |
| Flask/browser | No direct Chroma access | No direct Chroma access |

Agent tools live in `tools.py`; they enforce role-to-store permissions, while the raw Chroma client is only used in the retrieval and ingestion modules.
