# Multi-Agent Risk and Decision Analysis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to implement this plan task-by-task.

**Goal:** Use bounded AutoGen roles to classify each event, explain its company relevance, include Alpha Bank research, extrapolate percentage KPI impacts from analogues, propose alternatives, and return validated JSON.

**Architecture:** A Python controller owns the sequence, context, tool permissions, retries, and budget. AutoGen agents receive only role-specific inputs and tools; they exchange Pydantic-validated JSON rather than an open-ended group transcript. The critic verifies citations through exact-ID lookup.

**Tech Stack:** Existing AutoGen dependency, Pydantic 2, OpenAI-compatible RouterAI client (`https://routerai.ru/api/v1`, model `~z-ai/glm-flash-latest`), both Chroma retrieval wrappers, company/news services.

**Spec:** `company_news_pipeline/docs/superpowers/specs/2026-10-25-anonymized-company-news-design.md`

## Interfaces

- `analyze_company_news(synthetic_id: str, event_ids: list[str] | None = None) -> CompanyNewsAnalysis`
- `BudgetGate.reserve_call(role: str, model: str, estimated_tokens: int) -> BudgetDecision`
- `validate_analysis(payload: dict) -> CompanyNewsAnalysis`

## Agent Roster and Responsibilities

All roles use the configured RouterAI model through the Python controller. The controller passes each role only the fields listed below and validates every handoff as JSON. AutoGen does not broadcast the full conversation or tools to every agent.

| Specialist role | Responsibility and input | Output | Tools and data access |
|---|---|---|---|
| Company Context / Peer Analyst | Build the target context from the synthetic profile, payment-network aggregates, and already-ranked analogues; look up general industry and regional context. | Company context, peer cohort, feature-level similarity and missing-data notes. | SQL profile/peer service and privacy-filtered web search; no Chroma. |
| Search Planner | Turn target industry, peers, requested window and signal categories into per-ID searches. | Separate queries for industry news, court/crackdown signals, regulatory action and material facts. | Search-query generation only; no provider call and no Chroma. |
| News & Legal Researcher | Execute planned queries and open relevant primary sources. | Candidate articles and source extracts with URL, dates and retrieval provenance. | Serper News, Tavily fallback and bounded Playwright source opener; no Chroma. |
| Evidence Classifier | Normalize retrieved materials into events; identify subject, event date, geography and signal type. | Deduplicated structured facts classified as news, court, regulation, corporate material fact, macro/industry or other. | Retrieved articles/source text only; no search, SQL writes or Chroma. |
| Impact Analyst | Relate one classified event to target profile and peer/real-company analogues, then gather missing evidence. | Per-event risk/opportunity/mixed assessment, business KPI percentage range, horizon, confidence, assumptions and evidence. | Full read/search access to both Chroma stores and privacy-filtered Serper/Tavily web search with bounded source opening. |
| Bank Research Analyst | Find relevant Alpha Bank research and public context for the event/industry. | Bank view separated from factual evidence, with document/page citations. | Broad read/search in `alfa_research`; privacy-filtered web search and source opening. |
| Risk Methodology Analyst | Apply risk, uncertainty and decision-analysis methods to the event and proposed alternatives, consulting public methodology sources. | Method steps, scenario/uncertainty guidance and methodology citations. | Broad read/search in `risk_methodology`; privacy-filtered web search and source opening. |
| Action Analyst | Produce complete executable plans for one event; when evidence is insufficient, coordinate targeted work from specialist agents and resynthesize after review. | Multiple detailed plans with sequenced steps, owner, target/category, deadlines, cost/resources, completion criteria, fallback, KPI ranges, assumptions, citations and verification status. | Full read/search access to both Chroma stores and privacy-filtered Serper/Tavily web search with bounded source opening. |
| Critic / Source Checker | Independently check each event and action for source support, citation validity, date conflicts, supplier/category fit, attribution errors and execution completeness. | Verified/conditional/blocked status plus field-specific findings and targeted evidence requests. | Exact-ID Chroma citation lookup in both stores, privacy-filtered web search and source opening. |

The API/UI are not agents and receive only the final JSON. Ingestion workers are non-LLM processes with write access during explicit indexing jobs; they are not part of the agent roster. The complete store-access matrix remains in the design and the dual-Chroma plan.

## Tasks

### Task 1: Configure RouterAI inference, Wi-Fi egress, and budget gate

**Files:** Create `company_news_pipeline/news_analytics/llm_config.py`, `company_news_pipeline/news_analytics/budget.py`; modify `LOGIC/Setup_models.py` only through a compatible shared config adapter; update `.env.example` if present or create it.

- [ ] Configure `LLM_BASE_URL=https://routerai.ru/api/v1` and the exact model alias `~z-ai/glm-flash-latest`; reject other provider/model selections at startup and per call.
- [ ] Read `ROUTERAI_API_KEY` from environment; never write the key to logs or JSON.
- [ ] Ensure all agent roles share this one configured client/model unless a later user-approved change says otherwise.
- [ ] Record the requested alias and RouterAI's returned model/provider metadata when available; the `~...-latest` alias can move to a newer model version, so retain the actual response metadata with each analysis.
- [ ] Route only RouterAI destination traffic through the physical Wi-Fi interface. Resolve RouterAI host addresses at runtime and enforce scoped host routes through the Wi-Fi gateway; do not change global default routes. Detect DNS/address changes and reconcile scoped routes. If the OS refuses route creation or egress cannot be confirmed, fail closed rather than silently sending inference over another interface.
- [ ] Keep the route/interface implementation behind a small transport adapter so the app reports the selected interface without exposing credentials.
- [ ] Add a shared daily budget ledger capped at 500 ₽ across all roles; reserve budget before calls and stop analysis generation when exhausted.
- [ ] Record role, model alias, RouterAI usage/cost metadata when returned, estimated/actual usage and day-level cost without recording prompts containing secrets.

**Completion check:** The client targets the documented RouterAI base URL/model, missing API key produces a precise configuration error, and RouterAI calls are blocked when Wi-Fi-only egress cannot be enforced.

### Task 2: Define structured agent inputs and output models

**Files:** Create `company_news_pipeline/news_analytics/analysis/models.py`, `company_news_pipeline/news_analytics/analysis/prompts.py`.

- [ ] Define models for evidence, bank view, methodology references, event impact, metric percentage ranges, solution options, confidence, assumptions, citations, and analysis trace.
- [ ] Require an individual horizon per news event and per proposed solution.
- [ ] Add `verification_status` (`verified`, `conditional`, `blocked`) to each solution and a concise `collaboration_trace` of assigned roles, evidence IDs and Critic findings; exclude chain-of-thought.
- [ ] Model every solution as a complete execution plan: objective, specific target/item/category, numbered steps, responsible role, timing, dependencies, resources/cost, completion criteria, success metrics and fallback.
- [ ] For procurement recommendations, name supplier candidates separately for each relevant item/category when public evidence verifies category fit and geography; include source IDs and verification status.
- [ ] Treat product assortment and supplier fit inferred from analogues as assumptions until verified for the plan; include a validation step before changing spend or supplier allocation.
- [ ] If the target's assortment is unknown or no candidate can be verified, return a concrete information-gathering/qualification step and disclose the gap instead of inventing a supplier or claiming a relationship.
- [ ] Add structured `solution_gap_report`, `collaboration_task`, `candidate_evidence`, and `critic_review` handoff models so agents can request and contribute specific missing evidence.
- [ ] Have the controller assign gap tasks to relevant context/peer, search, news/legal, bank and methodology roles; collect cited findings and ask Action Analyst to assemble a revised complete plan.
- [ ] Require Critic to check the assembled plan independently and return field-specific findings; route failed fields to the responsible researcher and Action Analyst for targeted revision.
- [ ] Run up to three targeted search/review cycles per solution under shared tool, time and RouterAI budget limits; stop early when verified.
- [ ] Mark solutions `verified`, `conditional`, or `blocked`; identify RFQ, internal assortment, capacity, price or other confirmations that public sources cannot establish.
- [ ] Require a qualitative `risk`/`opportunity`/`mixed` label plus one or more KPI percentage ranges and direction.
- [ ] Always produce an extrapolated range when direct target data is insufficient; widen it and lower confidence when analogue coverage is weak, and include the analogue count and basis.
- [ ] Represent an analogue observation as supporting evidence, never as a fact about the synthetic target.
- [ ] Include separate `bank_view`, `risk_method_used`, and `ai_analysis` fields.

**Completion check:** A JSON object that omits per-event horizon, source provenance, or a solution impact range is rejected with field-specific validation details.

### Task 3: Implement role-specific AutoGen tools and orchestration

**Files:** Create `company_news_pipeline/news_analytics/analysis/agents.py`, `company_news_pipeline/news_analytics/analysis/orchestrator.py`.

- [ ] Implement the nine roles and JSON handoffs defined in the Agent Roster above.
- [ ] Give Impact Analyst and Action Analyst broad read/search tools for both `alfa_research` and `risk_methodology` stores.
- [ ] Give privacy-filtered web-search and bounded source-opening tools to Critic and every role with `Analyst` in its name; retain the existing tools for News & Legal Researcher.
- [ ] Use one server-side web gateway that removes synthetic IDs, graph identifiers and nonpublic exact financial/payment values from outbound queries, records provenance, and deduplicates repeated searches.
- [ ] Keep Chroma write/delete/reindex operations in the ingestion worker; agent access is full corpus read/search only.
- [ ] Keep Impact Analyst and Action Analyst handoffs structured even when they retrieve their own supporting evidence.
- [ ] Implement a bounded, controller-directed collaboration loop with up to three targeted search/review cycles per solution by default; continue until Critic verifies the plan or a concrete blocker/budget limit remains, without unbounded GroupChat handoffs.
- [ ] Ensure page text is treated as untrusted data and cannot issue instructions to tools or change role permissions.

**Completion check:** Each role receives only its declared inputs and tools; all intermediate results are JSON-serializable and traceable; a first-pass action gap triggers targeted multi-role research and Critic review before an incomplete plan can be returned.

### Task 4: Implement impact and action scenario estimates

**Files:** Create `company_news_pipeline/news_analytics/analysis/impact.py`, `company_news_pipeline/news_analytics/analysis/solutions.py`.

- [ ] Calculate context links from target profile, synthetic peers, Rusprofile analogues, news evidence, and Alpha research excerpts.
- [ ] Return risk/opportunity/mixed classification, severity/likelihood/confidence, evidence rationale, and event-specific horizon.
- [ ] For each KPI, return direction, `change_pct.min/max`, baseline basis, period, analogue references, and assumptions.
- [ ] For each solution, compute its expected KPI range relative to “no action,” with its own horizon, sequenced actions, owners, item/category, supplier evidence where relevant, completion criteria, fallback, costs/side effects, conditions and citations.
- [ ] Reject vague one-line actions that lack an execution sequence or measurable completion criteria.
- [ ] Do not accept an incomplete first-pass recommendation: invoke collaborative refinement, then return the best evidence-backed plan with any residual blockers explicit.
- [ ] Keep estimates scenario-based; no causal claim that an analogue's historical change was caused by the same event.

**Completion check:** A sparse-analogue input still returns a wide, low-confidence scenario range with explicit assumptions and analogue count.

### Task 5: Connect RAG/search inputs and persist the analysis trace

**Files:** Modify `company_news_pipeline/news_analytics/analysis/orchestrator.py`; create `company_news_pipeline/news_analytics/analysis/repository.py`.

- [ ] For each event, retrieve relevant Alpha excerpts and risk-methodology chunks through their assigned roles only.
- [ ] Store role inputs/outputs, selected source IDs, revisions, model aliases, budget result, and final JSON by synthetic ID/event ID.
- [ ] Persist solution gap reports, assigned collaboration tasks, candidate evidence IDs, Critic reviews, and final verification status for each solution.
- [ ] Do not persist hidden chain-of-thought; persist concise evidence, rationale, decisions, and trace metadata only.
- [ ] Reuse a valid saved analysis unless explicit re-analysis is requested or source/profile version has changed.

**Completion check:** The final object includes retrievable provenance for every bank/method quote and every external news citation.
