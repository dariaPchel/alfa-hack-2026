# Company Data and Peer Profiles — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to implement this plan task-by-task.

**Goal:** Create configurable mock versions of the anonymized hackathon CSVs until the real files arrive, then expose consistent company profiles, peer analogues, and payment-network signals by `SYNTHETIC_U`.

**Architecture:** Add focused import, repository, and matching modules under `news_analytics`. Store normalized source records in the operational SQL database; keep matching deterministic and return feature-level explanations.

**Tech Stack:** Python, pandas (already installed), SQLite, Pydantic 2 (already installed).

**Spec:** `company_news_pipeline/docs/superpowers/specs/2026-10-25-anonymized-company-news-design.md`

## Interfaces

- `load_hackathon_data(company_csv: Path, links_csv: Path, db: Database) -> ImportSummary`
- `get_company_profile(synthetic_id: str, db: Database) -> CompanyProfile | None`
- `find_peers(synthetic_id: str, db: Database, limit: int = 10) -> list[PeerProfile]`
- `get_counterparty_industries(synthetic_id: str, db: Database, limit: int = 10) -> list[IndustryExposure]`

## Tasks

### Task 1: Define normalized profile contracts and SQLite schema

**Files:** Create `company_news_pipeline/news_analytics/__init__.py`, `company_news_pipeline/news_analytics/models.py`, `company_news_pipeline/news_analytics/db.py`, `company_news_pipeline/news_analytics/schema.sql`.

- [x] Define Pydantic models `CompanyProfile`, `PeerProfile`, `IndustryExposure`, and `ImportSummary` from the exact fields in the hackathon PDF.
- [x] Create tables for synthetic company rows, person-company links, payment edges, import batches, peer scores, and schema warnings.
- [x] Preserve source values and nulls; do not coerce grades or flags into fabricated precise values.
- [x] Provide database initialization with a configurable path and idempotent schema creation.
- [x] Document the default local database path and how to override it.

**Completion check:** A fresh local database initializes and `CompanyProfile` serializes to JSON with optional fields intact.

### Task 2: Implement CSV schema inspection and import

**Files:** Create `company_news_pipeline/news_analytics/company_data.py`; modify `requirements.txt` only if the deployed runtime needs a missing CSV parser dependency.

- [x] Implement `load_hackathon_data(...)` for configurable CSV paths and UTF-8/UTF-8-SIG input.
- [x] Add a reproducible mock-data generator/fixture for both company and relation/payment CSVs using only synthetic IDs and clearly fabricated values; ensure referential links are internally consistent and mark files as mock data.
- [x] Validate required `SYNTHETIC_U` and recognize the optional profile fields listed in the design.
- [x] Inspect the relation file for person-company columns and payment columns; accept the documented layouts without assuming a real entity identifier.
- [x] Return row counts, skipped rows, missing optional fields, and column/schema warnings; reject duplicate synthetic IDs with a clear import error.
- [x] Store import batch and source filenames so the selected dataset version can be traced; persist a `mock_data` provenance flag and expose it in API/profile metadata.

**Completion check:** The CLI/import function reports a useful schema summary and does not fail solely because optional profile columns are absent.

### Task 3: Build company and payment-network profiles

**Files:** Create `company_news_pipeline/news_analytics/company_profiles.py`, `company_news_pipeline/news_analytics/payment_network.py`.

- [x] Implement `get_company_profile(...)` and derive top industries of payers/beneficiaries by total `PAY_AMT` and `PAY_CNT` using joined synthetic IDs and their `MAINOKVED_NAME`.
- [x] Derive concentration of top counterparties, group membership, exposure flags, and region summary without claiming temporal trends when the input has no dates.
- [x] Return the underlying contributing synthetic IDs and calculation basis in `IndustryExposure`/profile provenance.
- [x] Treat `SYNTHETIC_F` only as an anonymized graph node; never send its identifier to Serper, Tavily, or Rusprofile.

**Completion check:** Profile output includes its source ID, missing-field warnings, top counterparty industries, and the payment basis for each aggregate.

### Task 4: Implement deterministic peer matching

**Files:** Create `company_news_pipeline/news_analytics/peer_matching.py`, `company_news_pipeline/news_analytics/config.py`.

- [x] Implement `find_peers(...)` with configurable initial weights: OКВЭД 0.35, ownership/type 0.20, scale/revenue/headcount 0.20, region 0.10, age/stage 0.05, and product/trade/network exposure 0.10.
- [x] Match exact OКВЭД before broader prefix similarity; represent unavailable dimensions as unavailable, not as a mismatch.
- [x] Exclude the selected company itself; stable-sort ties by synthetic ID; return overall score and per-feature matches/misses.
- [x] Do not use an LLM to choose the peer cohort.

**Completion check:** Repeated input produces the same ordered peers and an explanation of every score contribution.

### Task 5: Add Rusprofile analogue candidate enrichment

**Files:** Create `company_news_pipeline/news_analytics/rusprofile_analogues.py`; reuse `PARSING/rusprofile.py` behind a narrow adapter.

- [x] Build query strings from industry/OКВЭД label, legal form, region, and size description; never use a synthetic ID as a company name or INN.
- [x] Retrieve candidates using the authorized Rusprofile session and extract profile ID, public profile URL, available financial years, corporate material-fact signals, and available legal/court indicators.
- [x] Re-rank candidates deterministically against `CompanyProfile`; retain query, matched features, profile URL, and retrieval time.
- [x] Label all returned real organizations as analogues; do not merge their legal facts into the selected synthetic company's own facts.
- [x] Return an empty/partial analogue set with an explicit source/session warning when Rusprofile access is unavailable.

**Completion check:** A profile can request analogue candidates without identifying the synthetic company as a real legal entity.
