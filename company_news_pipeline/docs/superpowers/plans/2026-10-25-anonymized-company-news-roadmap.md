# Anonymized Company News Analytics — Implementation Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to execute the selected sub-plan task-by-task. The roadmap links eight focused plans; follow the dependency order below.

**Goal:** Deliver a web prototype that turns each synthetic company profile and its analogues into source-grounded news, industry-risk signals, per-event impact estimates, and decision options returned as JSON.

**Architecture:** Keep the existing Flask application and add a focused `company_news_pipeline/news_analytics` package. Use one SQL operational store, two isolated persistent Chroma knowledge stores, a per-ID Serper News refresh process, and bounded AutoGen roles controlled by application code. The web UI consumes the same JSON API used by other clients. The root `news_analytics` package is a compatibility shim; the original Alpha PDFs, session state, and runtime vector data stay in ignored root data paths.

**Tech Stack:** Python, Flask, SQLite for the prototype operational store, Chroma, RouterAI `intfloat/multilingual-e5-large` embeddings, Serper News, Tavily supplementary search, Playwright source retrieval, AutoGen, [RouterAI OpenAI-compatible API](https://routerai.ru/docs/guides) using [`~z-ai/glm-flash-latest`](https://routerai.ru/models/~z-ai/glm-flash-latest), Flask templates and JavaScript.

**Spec:** `company_news_pipeline/docs/superpowers/specs/2026-10-25-anonymized-company-news-design.md`

## Global Constraints

- Never map a synthetic ID to a real company without an explicit source mapping; Rusprofile entities are analogues only.
- Keep `alfa_research` and `risk_methodology` physically separated and enforce the role access matrix in the design.
- Daily-refresh up to 20 results for 90 days and up to 20 for 7 days for every synthetic ID; search the last 24 hours for up to 10 results on every company-news request.
- Apply date cutoffs after provider retrieval; do not treat search results as complete court or regulator registries.
- For each news item and each proposed action, emit a scenario percentage range and its own evidence, assumptions, confidence, and horizon.
- Each proposed action must be a complete executable plan with concrete targets, sequenced steps, owners, timing and success criteria; named suppliers require public evidence and category/region fit.
- Use only the user-selected RouterAI model `~z-ai/glm-flash-latest` at `https://routerai.ru/api/v1`; total LLM cost remains capped at 500 ₽ per day.
- Route RouterAI inference traffic through the physical Wi-Fi interface only; do not change the machine's global default route, and fail closed if the scoped route cannot be enforced.
- Keep API keys and Rusprofile storage state outside source control; never log credentials or cookie values.
- Preserve existing `/api/news` and `/api/rusprofile` routes while adding the company-news API.
- Do not add automated test files or run tests in this plan; the implementation owner can add verification work only after an explicit user request.

## Plan Files and Dependency Order

1. [Rusprofile authenticated session](2026-10-25-rusprofile-auth-session-plan.md) — establishes the manually authenticated browser state needed for private/search pages; do not automate password entry.
2. [Company data and peer profiles](2026-10-25-company-data-peers-plan.md) — first creates configurable mock CSVs matching the hackathon schema, then establishes `CompanyProfile`, deterministic analogue scores, and payment-network aggregates; Rusprofile enrichment depends on step 1.
3. [Dual knowledge stores](2026-10-25-dual-chroma-knowledge-plan.md) — can proceed alongside steps 1–2; establishes retrieval contracts and role-specific Chroma tools.
4. [News collection and rolling windows](2026-10-25-news-collection-plan.md) — after step 2; produces persisted, per-ID news windows.
5. [AutoGen tool contracts and runtime](2026-10-25-autogen-tool-contracts-plan.md) — defines typed tool interfaces, execution policy and the role-to-tool matrix from steps 1–4.
6. [Agent analysis and JSON](2026-10-25-agent-analysis-plan.md) — after steps 2–5; consumes profiles, events, both retrieval stores, and the registered tool interfaces.
7. [Web API and interface](2026-10-25-web-news-interface-plan.md) — after step 6; integrates the app and presents the returned JSON.
8. [Docker image and deployment](2026-10-25-docker-deployment-plan.md) — after API, worker, tool and Chroma service interfaces are established; packages the runtime and persistent service graph.

## Cross-Plan Interfaces

- The data plan produces `CompanyProfile`, `PeerProfile`, and `get_company_profile(synthetic_id)` / `find_peers(synthetic_id, limit)`.
- The Rusprofile session plan produces a local Playwright storage state consumed by the narrow analogue adapter; this file is never an application response or source-control artifact.
- The knowledge plan produces `RetrievedChunk`, `retrieve_alfa(query, filters, limit)`, `retrieve_methodology(query, topic, limit)`, and citation lookup restricted to supplied chunk IDs.
- The news plan produces normalized `NewsEvent`, `SearchWindow`, `get_company_news(synthetic_id, refresh_24h)` and `refresh_company_windows(synthetic_id)`.
- The analysis plan consumes those interfaces and produces validated JSON through `analyze_company_news(synthetic_id, event_ids)`.
- The AutoGen tool plan produces `ToolRegistry`, typed `ToolSpec`/`ToolResult`, and `ToolExecutor` interfaces consumed by the agent-analysis plan.
- The web plan consumes the public API contract and does not query SQL or Chroma directly from the browser.
- The Docker plan packages the API, worker and ingestion commands into one image and runs the two Chroma stores with separate persistent volumes.

## Execution Boundaries

- Implement one sub-plan at a time in the listed dependency order; the knowledge-store ingestion can proceed independently once its source files are available.
- Completion checks in the sub-plans are observable acceptance conditions. Do not add automated test files or run tests unless the user explicitly requests that work.
- Keep the UI/API changes compatible with the existing Flask app and preserve existing `/api/news` and `/api/rusprofile` behavior.

## Inputs Needed Before End-to-End Execution

- The two hackathon CSV files are not present. Start with generated, clearly marked mock company/payment CSVs that match the PDF schema; replace them with real files when supplied without changing the import contract.
- RouterAI key is stored locally in the ignored `.env`; keep it out of commits and image layers.
- A Wi-Fi-scoped Windows route for RouterAI may require administrator privileges. This machine has an active Wi-Fi interface (`Беспроводная сеть`, index 8) and a competing `happ-xray` default route. Use narrow routes for RouterAI-resolved addresses through Wi-Fi; do not change global routing.
- The supplied analytics ZIP is the initial Alpha corpus (nine PDFs); Drive sync remains optional for later refreshes.

These inputs do not prevent implementation planning. The execution owner should request them before the dependent integration step rather than guessing.
