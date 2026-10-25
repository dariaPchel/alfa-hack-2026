# Web News API and Interface — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to implement this plan task-by-task.

**Goal:** Expose company selection, rolling news windows, event impact/decision JSON, and source transparency through the existing Flask application and a compact web interface.

**Architecture:** Add a Flask blueprint backed by the company/news/analysis service interfaces. Serve a Flask template and static assets; keep all collection and agent calls on the server and expose only validated response JSON to the browser.

**Tech Stack:** Existing Flask app, Jinja templates, vanilla JavaScript and CSS, JSON API.

**Spec:** `company_news_pipeline/docs/superpowers/specs/2026-10-25-anonymized-company-news-design.md`

## Interfaces

- `GET /api/companies -> CompaniesResponse`
- `GET /api/companies/<synthetic_id>/news -> CompanyNewsResponse` (includes a fresh last-24-hour Serper News request)
- `GET /api/companies/<synthetic_id>/news/<event_id> -> EventAnalysisResponse`
- `POST /api/companies/<synthetic_id>/analyze -> CompanyNewsAnalysis`
- `GET /news -> HTML dashboard`

## Tasks

### Task 1: Add the news analytics API blueprint

**Files:** Create `company_news_pipeline/news_analytics/api.py`; modify `webhook_server.py` to register the blueprint.

- [ ] Implement the four API routes from the design with request/response shapes defined by Pydantic models in earlier plans.
- [ ] Validate synthetic IDs and event ownership before returning data or triggering analysis.
- [ ] Preserve existing `/api/news/*`, `/api/rusprofile/*`, webhook, and health routes unchanged.
- [ ] Use consistent JSON errors with `success: false`, `error_code`, and a readable message; do not expose secrets or stack traces.
- [ ] Ensure request-time 24-hour refresh does not rerun daily 90/7 windows.

**Completion check:** Flask serves expected JSON fields for known IDs and returns 404 for unknown company/event IDs.

### Task 2: Build the company/news dashboard template

**Files:** Create `company_news_pipeline/templates/company_news.html`, `company_news_pipeline/static/company_news.css`, `company_news_pipeline/static/company_news.js`; add `GET /news` in `company_news_pipeline/news_analytics/api.py` or a dedicated page blueprint.

- [ ] Add synthetic ID selector and summary of industry, ownership, region, size, peer basis, and data gaps.
- [ ] Add three feed tabs: 90 days (up to 20), 7 days (up to 20), and 24 hours (up to 10); display each window's `updated_at` and actual count.
- [ ] Add per-event card: what happened, event type, source/date, why relevant, qualitative risk/opportunity, KPI change range, individual horizon, and confidence.
- [ ] Show `bank_view`, `risk_method_used`, `ai_analysis`, evidence, analogue basis, and solutions in visually separate sections.
- [ ] For each action, show its objective, supplier/category if relevant, numbered implementation steps, owner, target timing, completion criteria, resources/cost, fallback, KPI percentage range, assumptions and source references.
- [ ] Provide direct links to source URLs and page-level references to Alpha/method documents.
- [ ] Render API error and stale-data states without losing already loaded 90/7-day windows.

**Completion check:** A user can select an ID, change windows, open an event detail, and distinguish external fact, bank position, methodology, and AI analysis.

### Task 3: Add reproducible local run instructions

**Files:** Modify `README.md`; create/update `.env.example` and a sample synthetic dataset only if supplied by the user or already authorized for synthetic fixtures.

- [ ] Document environment configuration, input CSV paths, initial Chroma ingestion, daily worker invocation/schedule, Flask startup, and web URL.
- [ ] Document that all agent roles use RouterAI `~z-ai/glm-flash-latest`; read the key from local runtime configuration and never show it in the UI.
- [ ] Clearly state that generated mock CSVs are demo input and must be replaced by the real hackathon files when provided; include the source-provenance indicator in the UI.
- [ ] Do not include real Rusprofile credentials or session state in the repository.

**Completion check:** A new developer can follow the README to configure dependencies, load provided data, run the worker, start Flask, and open the dashboard.
