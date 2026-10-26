# Company news analytics: local and Docker runbook

> The active implementation is the Go stack in the repository root. The older Python/Flask instructions below are historical and are not used by `compose.p1.yaml`. For current startup steps, use the root README. The Go worker calls RouterAI using the runtime's ordinary route, sends `max_tokens=32000`, and has no internal LLM request-count or spend cap.
## Configuration

1. From the repository root, configure the root `.env` used by `compose.p1.yaml`; keep provider keys local and out of Git.
2. Set `LLM_BASE_URL=https://routerai.ru/api/v1`, `LLM_MODEL=~z-ai/glm-flash-latest`, and `LLM_API_KEY`. The active Go worker sends `max_tokens=32000` and `reasoning.effort=low`, with the existing 50-second timeout and no application-level request or spend cap.
3. Docker Desktop uses the host runtime's ordinary network route for RouterAI; no Wi-Fi-specific proxy is configured.
4. `SERPER_API_KEY` is used by the separate Go news worker. No embedding service is required by the active Go stack.


## Data and indexing

The bundle has 24 reproducible mock companies and mock relation/payment rows in `company_news_pipeline/data/mock`. Regenerate them with:

```powershell
python -m news_analytics.mock_data --output-dir company_news_pipeline/data/mock --company-count 24 --seed 20261025
```

The nine supplied Alpha PDFs are extracted under root `data/alfa_research`; their hashes and Drive folder provenance are in `company_news_pipeline/news_analytics/knowledge/sources.json`. PDF files are ignored by Git and mounted separately from the application image. Initialize the SQLite schema and import the mocks with:

```powershell
python -m news_analytics.company_data --companies company_news_pipeline/data/mock/df_Uid_data_hack.csv --relations company_news_pipeline/data/mock/df_Fid_Uid_link_hack.csv --mock-data
```

Index Alpha pages and authorized methodology excerpts:

```powershell
python -m news_analytics.knowledge.ingest_alfa
python -m news_analytics.knowledge.ingest_methodology
```

`company_news_pipeline/news_analytics/knowledge/methodology_sources.json` lists official ISO, COSO, UK Government, NIST, and Federal Reserve sources and their jurisdiction/license limits. Concise, locally authored summaries with attribution are already in `company_news_pipeline/data/methodology_sources` and will be indexed. Full copyrighted ISO/COSO standards are not fetched or copied. The summaries are methodological aids, not legal requirements or complete reproductions of the sources.

The local prototype defaults to independent `PersistentClient` directories under `data/vectorstores/alfa_research` and `data/vectorstores/risk_methodology`. Docker uses two separate Chroma server services, collections, and persistent volumes. A collection is searchable only after successful nonempty ingestion adds `ingestion_ready=true` metadata.

## News collection and API

Start the existing Flask application (which preserves the old APIs and adds the company-news blueprint):

```powershell
python webhook_server.py
```

Open `http://127.0.0.1:5000/news`. The API includes `GET /api/companies`, `GET /api/companies/{id}/news`, `GET /api/companies/{id}/news/{event_id}`, and `POST /api/companies/{id}/analyze`.

The daily worker refreshes 90-day and 7-day sets for every synthetic ID, up to 20 events per window. Run it once with `python -m news_analytics.search.worker`, or run `python -m news_analytics.search.scheduler` to wait for the configured 06:00 `Europe/Moscow` refresh each day. Every company-news request separately searches the last 24 hours for up to 10 dated events. `NEWS_ANALYTICS_MAX_QUERIES_PER_ID` caps queries per ID/window; `NEWS_ANALYTICS_REFRESH_WORKERS` caps parallel company jobs. Provider results are post-filtered against exact cutoffs; undated results are retained as rejected candidates with reasons, not placed into a rolling date window.

The analysis controller uses bounded AutoGen roles, stores a concise trace without chain-of-thought, and caps the daily RouterAI estimate ledger at 500 RUB. Each event is analyzed separately. Action Analyst receives up to three targeted research/review cycles with Critic; incomplete or unverified supplier actions remain conditional/blocked and must expose their gaps. `open_source_page` supports a browser-rendered mode (`render_js: true`) for public JavaScript pages; it uses a cookie-free context and validates/limits navigation requests.

## Docker Desktop

Place the supplied Alpha PDFs in `data/alfa_research`, configure `.env` with the RouterAI and Serper keys, then start the persistent services from the repository root:

```powershell
docker compose --project-directory . --env-file .env -f company_news_pipeline/compose.yaml up -d chroma-alfa chroma-methodology
docker compose --project-directory . --env-file .env -f company_news_pipeline/compose.yaml --profile ingest run --rm ingest
docker compose --project-directory . --env-file .env -f company_news_pipeline/compose.yaml up -d api news-worker
```

The API is published on `NEWS_API_BIND`/`NEWS_API_PORT` (default loopback port 5000). Chroma ports are internal only. The scheduler container refreshes historical windows independently of API traffic. The API refreshes only the 24-hour window on requests. The `ingest` profile initializes SQL, imports mock CSVs, indexes Alpha PDFs and reports missing methodology excerpts.

Persistent paths are Docker volumes `analytics-data`, `alfa-chroma`, and `methodology-chroma`. Back them up while services are stopped or using a consistent volume snapshot. Restore the volumes before starting API/worker. SQLite is single-host only; migrate the operational store to PostgreSQL and coordinate worker schedules before adding API replicas.

## Operations and recovery

- `docker compose --project-directory . --env-file .env -f company_news_pipeline/compose.yaml ps` and the matching `logs --tail=200 api news-worker chroma-alfa chroma-methodology` command show service health and warnings. Provider keys/cookies must never be placed in logs.
- If a Chroma service is unavailable, retrieval returns an explicit store error; restart the affected Chroma service and verify its persistent volume before reindexing.
- If the Rusprofile session expires, recreate it manually on the host and restart API/worker containers to mount the refreshed read-only state.
- If the worker misses a scheduled run, execute `docker compose --project-directory . --env-file .env -f company_news_pipeline/compose.yaml exec news-worker python -m news_analytics.search.worker` once. Existing successful windows remain in SQLite if another window fails.
- Roll back by restoring the previous image tag and the matching SQL/Chroma volume snapshot. Do not run ingestion against a restored database with a newer incompatible schema until the migration path is reviewed.

## Known implementation boundaries

- The legacy Rusprofile parser currently returns its leading match per query; the adapter labels it as an analogue and warns that a real candidate cohort still requires a multi-result parser.
- The local Drive folder refresh connector is not authenticated or implemented as an API sync. The supplied archive and its local hash manifest are usable; Drive refresh requires a credentialed connector.
- Methodology notes are short original summaries; confirm their source pages and jurisdiction limits before relying on them, and replace them only with licensed or otherwise authorized texts.
- RouterAI requests use the ordinary network route available to the host/Docker runtime; there is no Wi-Fi-specific proxy in the active Go stack.
