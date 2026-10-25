# Company news analytics: local and Docker runbook

## Configuration

1. From the repository root, copy `company_news_pipeline/.env.example` to `.env` and set the RouterAI, Serper, and optional Tavily keys. Keep `.env` local.
2. Install the project dependencies from `requirements.txt`. The project uses the RouterAI model alias `~z-ai/glm-flash-latest` at `https://routerai.ru/api/v1`; the application rejects a missing RouterAI key and does not select a fallback model.
3. Set `ROUTERAI_API_KEY` and the RouterAI egress route. The app uses `intfloat/multilingual-e5-large` through RouterAI's `/api/v1/embeddings`; no local model download is needed. PDF excerpts and methodology notes are sent to the embedding provider for vectorization. Embedding usage shares the 500 RUB/day RouterAI budget with chat inference.
4. Create a Rusprofile session with `python save_rusprofile_session.py`, sign in manually in the visible browser, then close it to save `.local/rusprofile_storage_state.json`. The session file is ignored by Git.

On Windows local runs, the RouterAI model config adds `/32` routes for the resolved RouterAI addresses through the active physical Wi-Fi interface in `ActiveStore`. It checks the selected interface before creating the model configuration. It never changes the machine's default route. If route installation/verification fails, inference fails closed.

For Docker Desktop, run the host-only RouterAI egress proxy from an elevated PowerShell session after setting `ROUTERAI_PROXY_USER` and `ROUTERAI_PROXY_PASSWORD` in the host environment. Both API inference and the ingestion job use this proxy for chat and embedding requests:

```powershell
python -m news_analytics.wifi_egress_proxy
```

The proxy accepts only authenticated `CONNECT routerai.ru:443` traffic, binds outbound TCP to the Wi-Fi IPv4 address, and verifies the scoped destination route before connecting. Configure the Windows firewall so the proxy port `18128` is reachable from Docker Desktop only. Set `ROUTERAI_EGRESS_PROXY` in `.env` to `http://user:password@host.docker.internal:18128`; URL-encode special characters in the credentials. Do not expose the proxy port to the public internet.

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

Open `http://127.0.0.1:5000/news`. The API includes `GET /api/companies`, `GET /api/companies/{id}/news`, `GET /api/companies/{id}/news/{event_id}`, `POST /api/companies/{id}/analyze`, and `POST /api/companies/{id}/pipeline` for the unified v1 response schema.

The daily worker refreshes 90-day and 7-day sets for every synthetic ID, up to 20 events per window. Run it once with `python -m news_analytics.search.worker`, or run `python -m news_analytics.search.scheduler` to wait for the configured 06:00 `Europe/Moscow` refresh each day. Every company-news request separately searches the last 24 hours for up to 10 dated events. `NEWS_ANALYTICS_MAX_QUERIES_PER_ID` caps queries per ID/window; `NEWS_ANALYTICS_REFRESH_WORKERS` caps parallel company jobs. Provider results are post-filtered against exact cutoffs; undated results are retained as rejected candidates with reasons, not placed into a rolling date window.

The analysis controller uses bounded AutoGen roles, stores a concise trace without chain-of-thought, and caps the daily RouterAI estimate ledger at 500 RUB. Each event is analyzed separately. Action Analyst receives up to three targeted research/review cycles with Critic; incomplete or unverified supplier actions remain conditional/blocked and must expose their gaps. `open_source_page` supports a browser-rendered mode (`render_js: true`) for public JavaScript pages; it uses a cookie-free context and validates/limits navigation requests.

### Run the full pipeline for one company

After the data/indexing setup and API are ready, populate the 90-day and 7-day history once (the scheduler then keeps it fresh daily):

```powershell
docker compose --project-directory . --env-file .env -f company_news_pipeline/compose.yaml run --rm news-worker python -m news_analytics.search.worker
```

Then invoke the unified pipeline endpoint. It refreshes the last 24 hours, combines those results with the stored 7-day/90-day windows, loads the available Rusprofile analogue, runs the per-event analysis and returns the v1 JSON schema. Omit `event_ids` to analyze up to the 20 newest available events for that company:

```powershell
$companies = Invoke-RestMethod http://127.0.0.1:5000/api/companies
$id = $companies.companies[0].synthetic_id
$result = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:5000/api/companies/$id/pipeline" `
  -ContentType 'application/json' -Body '{}'
$result | ConvertTo-Json -Depth 50
```

The response includes rolling-window counts/timestamps, peer basis, source catalog, available court/regulatory/material-fact search signals, Alpha Bank view, methodology references, per-news impact estimates, complete action plans, and warnings. To collect and inspect news without running the LLM analysis, call `GET /api/companies/{id}/news`. To analyze only selected events, pass `{"event_ids":["<24-character-event-id>"]}` to either `POST /analyze` or `POST /pipeline`. Court signal counts describe categorized search results; they do not establish an increase in enforcement without a comparable baseline.

## Docker Desktop

Place the supplied Alpha PDFs in `data/alfa_research`, configure `.env` including the host Wi-Fi proxy, then start the persistent services from the repository root:

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
- Docker Desktop requires the host Wi-Fi egress proxy for RouterAI. Linux deployments need an equivalent host-bound proxy or platform-specific route implementation; direct fallback is not enabled.
