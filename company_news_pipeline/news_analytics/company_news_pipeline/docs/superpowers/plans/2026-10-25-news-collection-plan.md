# Per-Company News Collection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to implement this plan task-by-task.

**Goal:** Collect and persist separate Serper News results for every synthetic company, maintain daily 90/7-day windows, and retrieve the latest 24-hour window on each company-news request.

**Architecture:** Extend the existing Serper module with the News vertical and normalize provider responses into a stable event schema. Store event records and per-company query provenance in SQLite. Run daily historical refresh as a separate worker command; the Flask request path performs a fresh 24-hour lookup.

**Tech Stack:** Python requests, Flask, SQLite, Serper News, Tavily supplementary search, Playwright only for reading selected source URLs.

**Spec:** `company_news_pipeline/docs/superpowers/specs/2026-10-25-anonymized-company-news-design.md`

## Interfaces

- `search_serper_news(query: str, max_results: int = 20, time_filter: str | None = None) -> ProviderSearchResult`
- `normalize_news_result(raw: dict, retrieved_at: datetime) -> NewsEvent | None`
- `refresh_company_windows(synthetic_id: str, profile: CompanyProfile) -> RefreshSummary`
- `get_company_news(synthetic_id: str, refresh_24h: bool = True) -> CompanyNewsResponse`
- `run_daily_refresh(company_ids: list[str] | None = None) -> DailyRefreshSummary`

## Tasks

### Task 1: Add the News provider adapter

**Files:** Modify `SERPER_SEARCH.py`; create `company_news_pipeline/news_analytics/search/models.py`, `company_news_pipeline/news_analytics/search/serper_news.py`.

- [ ] Preserve existing `search_serper` and `search_serper_fast` behavior for other callers.
- [ ] Add a distinct Serper News adapter using the News response field and existing `SERPER_API_KEY` environment convention.
- [ ] Normalize article title, canonical URL, snippet, publisher, provider date, image URL, provider rank, query, and retrieval timestamp.
- [ ] Parse provider-relative dates where possible; post-filter strictly against the requested cutoff and return undated/unparseable items with an explicit date status, outside exact windows.
- [ ] Apply rate limit, timeout, bounded retry, and structured error handling without exposing the API key.

**Completion check:** Existing generic Serper calls remain unchanged, while the new adapter returns normalized news items and explicit provider errors.

### Task 2: Add event persistence and deduplication

**Files:** Create `company_news_pipeline/news_analytics/search/repository.py`, `company_news_pipeline/news_analytics/search/dedup.py`; modify `company_news_pipeline/news_analytics/db.py`, `company_news_pipeline/news_analytics/schema.sql`.

- [ ] Store a canonical event once by canonical URL, with a content fingerprint fallback for URL variants.
- [ ] Store every query/run separately and link each event to each synthetic ID with its matched search query, profile reasons, date window, first/last seen times, and selection rank.
- [ ] Keep the same event visible in multiple windows without duplicating the event row.
- [ ] Preserve rejected candidates and rejection reasons for traceability.
- [ ] Persist provider dates and parsed dates independently.

**Completion check:** One canonical article can be associated with multiple companies/windows while being stored once.

### Task 3: Build company-specific query plans and daily 90/7 refresh

**Files:** Create `company_news_pipeline/news_analytics/search/query_plan.py`, `company_news_pipeline/news_analytics/search/refresh.py`, `company_news_pipeline/news_analytics/search/worker.py`.

- [ ] Build queries per synthetic ID from main OKVED, top counterparty industries, region, size/exposure flags, and signal categories: courts, material facts, regulator actions, and general industry events.
- [ ] Preserve per-ID query plans; do not substitute a shared cohort search for an individual ID search.
- [ ] For each ID, refresh 90-day and 7-day candidate sets daily; deduplicate/rank across subqueries and keep up to 20 per window.
- [ ] Store a run record and last-success/error status per ID/window.
- [ ] Add a standalone worker command that can run once and be called by an OS/container scheduler; default schedule is 06:00 Europe/Moscow and can be overridden by environment.
- [ ] Add bounded concurrency and configurable request/Serper budget so a large input dataset cannot launch unbounded queries.

**Completion check:** The worker processes each supplied ID independently and records partial failures without discarding earlier successful windows.

### Task 4: Implement fresh 24-hour retrieval

**Files:** Modify `company_news_pipeline/news_analytics/search/refresh.py`; create `company_news_pipeline/news_analytics/search/service.py`.

- [ ] Implement `get_company_news(..., refresh_24h=True)` to perform a fresh query for the selected ID's last 24 hours on each company-news request.
- [ ] Normalize and strict-filter dates; deduplicate/rank across category subqueries; return up to 10 news items.
- [ ] Update persisted event links and keep historical 90/7-day snapshots independent of the fresh request.
- [ ] Return actual result count and warnings when fewer than the requested cap are available.

**Completion check:** A request returns fresh 24-hour results alongside stored 90/7-day windows and explicit timestamps for each window.

### Task 5: Preserve existing news routes and expose service interface

**Files:** Keep existing `news_api.py` routes compatible; create `company_news_pipeline/news_analytics/api.py` in the web plan rather than coupling search internals to Flask.

- [ ] Keep `/api/news/search` and `/api/news/queries` as existing compatibility routes.
- [ ] Keep Serper/Tavily/provider logic independent from Flask request globals.
- [ ] Document environment variables and worker invocation in the module docstrings/config sample.

**Completion check:** Existing clients retain their prior request/response behavior, and new company-news code can call the provider service without importing Flask.
