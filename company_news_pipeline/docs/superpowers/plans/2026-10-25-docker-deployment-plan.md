# Docker Image and Service Deployment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to execute this plan task-by-task.

**Goal:** Build one reproducible application image and a Compose deployment for the Flask API, scheduled news worker, ingestion jobs and two persistent Chroma stores.

**Architecture:** Build one immutable application image reused by separate API and worker containers with different commands. Run the two Chroma stores as separate services and volumes. Keep application data, source PDFs, embeddings and the Rusprofile session outside the image. Use the host `.env` only for runtime configuration and secrets. Keep the deployment single-host/single-API until the operational database is migrated for horizontal scaling.

**Tech Stack:** Docker BuildKit, Docker Compose v2, Python slim runtime, Gunicorn, Chroma server, SQLite prototype database, Playwright Chromium, RouterAI-hosted multilingual embedding model.

**Spec:** `company_news_pipeline/docs/superpowers/specs/2026-10-25-anonymized-company-news-design.md`

**References:** [Docker build best practices](https://docs.docker.com/build/building/best-practices/), [multi-stage builds](https://docs.docker.com/get-started/docker-concepts/building-images/multi-stage-builds/), [Compose secrets](https://docs.docker.com/reference/compose-file/secrets/), [Compose startup order and healthchecks](https://docs.docker.com/compose/how-tos/startup-order/).

## Deployment Layout

| Service | Image/command | Persistent data | Purpose |
|---|---|---|---|
| `api` | Application image; Gunicorn serving `webhook_server:app` | SQL data volume; optional model cache | Existing APIs and company-news API/UI. |
| `news-worker` | Same application image; daily refresh command | SQL data volume; model cache | Independently refresh 90/7-day windows for each synthetic ID. |
| `ingest` | Same application image; one-shot ingestion command | Both Chroma endpoints; source input mounted read-only | Import CSV/archive and index/update sources. Run explicitly. |
| `chroma-alfa` | Pinned Chroma server image | Dedicated Alpha volume | `alfa_research` collection only. |
| `chroma-methodology` | Pinned Chroma server image | Dedicated methodology volume | `risk_methodology` collection only. |

The initial Compose setup is one API replica and one daily worker. SQLite is placed on a named local volume and shared only by these same-host containers. Horizontal or multi-host deployment requires moving SQL state to PostgreSQL and keeping each worker's refresh lock/distributed schedule coordinated.

## Image and Runtime Requirements

- Use a pinned Python slim base image and pinned dependency lock; build a wheel/dependency stage and copy runtime artifacts into the final stage.
- Install the system libraries required by `lxml`, the chosen PDF reader and headless Playwright Chromium. Keep compilers and build-only packages out of the final stage.
- Run as a dedicated non-root UID, use exec-form entrypoints, forward SIGTERM, and configure graceful shutdown for Gunicorn and the worker.
- Use Gunicorn for the Flask API; the Flask development server is not the container production command.
- Use RouterAI embeddings through the same Wi-Fi-only egress path as chat inference; record the model ID and vector dimension in each Chroma collection and do not mount a local model cache.
- Do not include `.env`, `.git`, `.local/rusprofile_storage_state.json`, CSVs, source PDFs/ZIPs, local databases, Chroma data, model caches, `__pycache__`, generated reports or temporary outputs in the Docker build context.
- Do not place API keys, cookies, or Rusprofile storage state in Dockerfile `ARG`/`ENV`, image layers, labels, logs or build arguments.
- Mount RouterAI credentials at runtime. For local Compose, load `.env` for interpolation and pass only `ROUTERAI_API_KEY` to the API/worker; production may use the target platform's secret mount. The application config supports env var or secret-file input.
- Mount Rusprofile storage state read-only only to services that need analogue retrieval. Allow session absence/expiry to produce an explicit warning and partial analysis.
- Mount the nine Alpha PDFs or extracted source folder read-only to `ingest`; keep the archive and extracted documents out of the application image.
- Expose only the configured API port. Chroma services remain internal to the Compose network.

## Wi-Fi Egress Requirement

The RouterAI API traffic must leave through the physical Wi-Fi interface while unrelated host traffic keeps its existing routes. Docker Desktop on Windows adds NAT/VM networking, so the implementation must verify how the host's scoped RouterAI address routes apply to container egress. Add narrow routes for resolved RouterAI addresses through the Wi-Fi gateway or use a controlled host egress proxy bound to Wi-Fi if Docker Desktop bypasses the intended host route. Keep the global default route unchanged. The application must fail closed if it cannot establish/verify the RouterAI path, and it must not silently fall back through `happ-xray`.

## Tasks

### Task 1: Prepare deterministic Python runtime

**Files:** Create/update `requirements.lock` (or the selected lock file), `Dockerfile`, `.dockerignore`; modify `requirements.txt` as needed; add Gunicorn if missing.

- [ ] Resolve and pin the exact AutoGen distribution/API family required by the existing `autogen` imports and planned tool adapter.
- [ ] Pin Python base image, runtime dependencies, PDF parsing, Chroma client, Playwright package and embedding runtime versions.
- [ ] Use BuildKit multi-stage installation with cache-efficient dependency copy order and a non-root final user.
- [ ] Install Chromium and OS libraries at image build time; do not perform browser/model downloads in the API container entrypoint.
- [ ] Add `.dockerignore` exclusions for secrets, local session state, data archives, databases, vector data, model cache, VCS and generated files.
- [ ] Add exec-form commands/entrypoints for `api`, `worker`, and one-shot `ingest` modes using the same image.

**Completion check:** The image definition is deterministic, contains no local secrets/data inputs, and can start each process mode from a clean runtime.

### Task 2: Define the Compose service graph and persistent volumes

**Files:** Create `company_news_pipeline/compose.yaml`; create or modify service entrypoint/config files as needed.

- [ ] Define `api`, `news-worker`, `chroma-alfa`, and `chroma-methodology` with internal DNS service names and dependency health conditions.
- [ ] Define separate named volumes for SQL state and Alpha/methodology Chroma persistence; embeddings are provided remotely by RouterAI.
- [ ] Ensure the two Chroma containers use separate storage paths and credentials/network boundaries where supported.
- [ ] Add an explicit one-shot ingestion profile/command that exits after success and retains detailed source-level errors.
- [ ] Pass only required environment values/secrets to each service; keep raw `.env` out of the image and avoid forwarding unrelated provider keys.
- [ ] Set restart behavior, healthchecks, resource ceilings and log rotation appropriate for the single-host prototype.
- [ ] Keep Chroma ports private; expose the API port according to the configured local/reverse-proxy deployment.

**Completion check:** The Compose graph clearly separates API, worker, ingestion and both vector stores, with persistent independent data.

### Task 3: Add persistent inputs and initialization procedure

**Files:** Modify `README.md`; create deployment scripts/configuration only as needed.

- [ ] Document creation of the `.env` runtime configuration without copying credentials into the repository.
- [ ] Document mounting the Rusprofile storage state as a read-only secret/input only for services that need it.
- [ ] Document first-run sequence: initialize SQL schema, import mock CSVs, ingest Alpha ZIP PDFs and methodology sources, then start API and scheduled worker.
- [ ] Ensure the scheduled worker refreshes 90/7-day windows independently of API traffic; the API performs only the configured 24-hour search on request.
- [ ] Keep source PDFs, CSVs and vector/SQL persistence recoverable from host volumes; document backup and restore paths.
- [ ] Document that this Compose profile runs as one API/worker host with SQLite; specify PostgreSQL migration before multi-host replicas.

**Completion check:** A new operator can create persistent state, initialize data once, start the stack, and restart it without losing indexed or operational data.

### Task 4: Enforce runtime network and secret boundaries

**Files:** Modify `company_news_pipeline/compose.yaml`, `company_news_pipeline/news_analytics/config.py`, RouterAI transport and deployment documentation.

- [ ] Forward `ROUTERAI_API_KEY` only to API and worker, and configure the app to read it from runtime env or mounted secret file.
- [ ] Keep provider credentials, Rusprofile cookies and source content out of logs and health responses.
- [ ] Verify RouterAI DNS/IP route and Wi-Fi egress from the Dockerized API/worker on Windows Docker Desktop; add scoped host routes or a Wi-Fi-bound egress proxy if needed.
- [ ] Keep the global host default route unchanged and fail closed when the configured Wi-Fi egress path is unavailable.
- [ ] Restrict service-to-service network paths so only API/worker/ingest can connect to the required Chroma stores, SQL volume, and outbound source providers.

**Completion check:** Deployment notes demonstrate the intended RouterAI egress path and each runtime secret is present only where needed.

### Task 5: Define image release and operations

**Files:** Modify `README.md`; create a deployment runbook under `docs/deployment/`.

- [ ] Document build, tag, compose startup/stop, ingestion, worker logs, health inspection, backup and rollback commands.
- [ ] Pin release images by immutable tag/digest and record the source revision, Python/AutoGen/Chroma versions, and embedding-model revision.
- [ ] Include image vulnerability review and dependency update cadence before production release.
- [ ] Document resource sizing for Chromium, Chroma and parallel agent calls; keep embedding and chat spend within the existing 500 ₽/day RouterAI budget.
- [ ] Define recovery behavior for unhealthy API, worker, either Chroma store, SQL volume and expired Rusprofile session.

**Completion check:** A deployment can be rebuilt from a known source revision and its persistent data can be backed up and restored using the runbook.
