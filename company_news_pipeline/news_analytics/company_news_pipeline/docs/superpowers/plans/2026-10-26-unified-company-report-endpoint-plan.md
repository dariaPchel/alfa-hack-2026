# Unified Company Report Endpoint Implementation Plan

**Goal:** Add one company endpoint that returns the supplied v1 report shape by combining rolling news windows, per-event analysis, peer context, source provenance, and available industry signals.

**Architecture:** Keep the existing news and analysis services. Add a report serializer and a `POST /api/companies/{synthetic_id}/pipeline` route that refreshes 24-hour news, optionally loads one Rusprofile analogue, invokes the existing per-event analysis, then assembles the final response from persisted windows and validated analysis models. Missing sources remain empty with warnings; no fake counts or source claims.

**Tech Stack:** Python, Flask, Pydantic models already used by `news_analytics`, SQLite repositories, existing Rusprofile and Serper adapters.

**Output contract:** The requester-provided v1 JSON contract (2026-10-25) with top-level keys `schema_version`, `request_id`, `synthetic_id`, `generated_at`, `model`, `windows`, `peer_basis`, `industry_signals`, `sources`, `bank_view`, `risk_method_used`, `ai_analysis`, `events`, `analysis_trace`, and `warnings`; map internal numeric confidence/likelihood and KPI ranges to the requested qualitative/range format.

## Files

- Create `company_news_pipeline/news_analytics/report.py` for pure response assembly and structured industry-signal aggregation.
- Modify `company_news_pipeline/news_analytics/api.py` to validate input and expose the pipeline route.
- Modify `company_news_pipeline/news_analytics/analysis/orchestrator.py` to accept and include the retrieved Rusprofile analogue context.
- Modify `company_news_pipeline/docs/company-news-runbook.md` with request and response usage.

## Constraints

- Do not refresh 7-day/90-day windows on request; the daily worker owns those. Refresh 24-hour news on each pipeline call.
- Omit unavailable facts, return zero only for measured counts, and include warnings for unavailable Rusprofile/session or stale/missing historical windows.
- Keep every impact and solution attached to its source event and citations.
- Do not expose chain-of-thought or secrets.
- Verification is static (Python AST, JSON/route configuration review); do not add or run automated tests.

## Steps

1. Add a serializer that maps stored windows, validated `CompanyNewsAnalysis`/`NewsImpact`/`SolutionPlan` data, peers, citations, and structured query categories into the v1 response.
2. Add the POST route, request validation, 24-hour refresh, optional Rusprofile enrichment, analysis call, and source-report assembly. Pass the analogue result into the analysis context.
3. Document the endpoint and validate Python syntax, JSON manifests, and Compose configuration without launching services.
