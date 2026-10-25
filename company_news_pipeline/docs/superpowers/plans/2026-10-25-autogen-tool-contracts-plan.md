# AutoGen Tool Contracts and Runtime — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to execute this plan task-by-task.

**Goal:** Define safe, typed, auditable tools for the nine AutoGen roles, with explicit permissions for SQL, Rusprofile, web search, source opening, and both Chroma stores.

**Architecture:** Keep tool implementations as ordinary server-side Python services. A central registry binds versioned Pydantic input/output contracts to role allowlists and policy middleware; an AutoGen adapter registers only the permitted functions on each role. The Python controller owns execution order, budgets, concurrency, retries, and provenance.

**Tech Stack:** Existing `autogen` 0.10.x dependency/API, Pydantic 2, Flask service layer, Serper, Tavily, Playwright, Rusprofile session adapter, Chroma retrieval wrappers.

**Spec:** `company_news_pipeline/docs/superpowers/specs/2026-10-25-anonymized-company-news-design.md`

## Compatibility Decision

The repository currently uses the `autogen` import and `AssistantAgent.register_function(...)` style. The new tool layer must use the exact distribution/version resolved from `requirements.txt`; do not mix the current repository API with Microsoft AutoGen AgentChat examples that use `autogen_agentchat`/`FunctionTool`. Keep the package-specific registration in one adapter so the tool contracts remain framework-independent. Official references: [AG2 tool overview](https://classic.docs.ag2.ai/latest/docs/user-guide/advanced-concepts/tools/basics/) and [AutoGen AgentChat tool behavior](https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.agents.html).

## Tool Contract

Each tool has a stable name and version, one-line purpose, Pydantic request model, Pydantic response model, timeout, retry policy, role allowlist, and provenance requirements. Tool results use a common envelope: `status`, typed `data`, `sources`, `warnings`, `error_code`, `request_id`, and `elapsed_ms`. Error responses contain no traceback, credential, cookie, or provider secret.

Tool outputs support collaboration handoffs: researchers return `candidate_evidence` tied to a requested gap, while Critic returns field-specific `critic_review` findings. The controller routes findings only to the roles responsible for resolving them.

| Tool | Purpose and core inputs | Result/provenance | Roles |
|---|---|---|---|
| `get_company_profile` | Load one `synthetic_id` from the SQL profile service. | Profile version, data gaps, synthetic provenance. | Company Context / Peer Analyst; controller. |
| `find_peer_companies` | Return deterministic synthetic peers and feature scores. | Peer IDs, feature contributions and source dataset version. | Company Context / Peer Analyst; controller. |
| `get_industry_payment_exposure` | Read payer/beneficiary industry aggregates. | Aggregate basis, date coverage, synthetic-node references. | Company Context / Peer Analyst; Impact Analyst; Action Analyst. |
| `search_rusprofile_analogues` | Search by industry, legal form, region and size; never pass a synthetic ID as an entity identifier. | Candidate Rusprofile IDs/URLs, analogue score, query and retrieval time. | Company Context / Peer Analyst; Impact Analyst; Action Analyst. |
| `get_rusprofile_analogue_profile` | Fetch a selected public analogue profile via the saved session adapter. | Extracted profile fields, material facts/court signals, URL, retrieval time and session warning. | Company Context / Peer Analyst; Impact Analyst; Action Analyst. |
| `search_news` | Serper News query for an ID-scoped window and category. | Normalized candidates with URL, publication date, provider, query and retrieval time. | News & Legal Researcher; all Analyst roles; Critic / Source Checker. |
| `search_web` | Privacy-filtered Serper/Tavily web search for public context, supplier candidates by procurement category/region, or source verification. | Ranked results with provider/query/URL/date provenance; supplier candidates remain unverified until source/page checks establish fit. | Company Context / Peer, Impact, Bank Research, Risk Methodology, Action Analysts; Critic / Source Checker; News & Legal Researcher. |
| `open_source_page` | Fetch a candidate public URL using bounded Playwright retrieval. | Sanitized text excerpt, final URL, title, date hints, status and retrieval time. | News & Legal Researcher; all Analyst roles; Critic / Source Checker. |
| `retrieve_alfa_research` | Semantic retrieval in the whole `alfa_research` corpus. | Chunks with store ID, document, page, version/hash and citation. | Bank Research Analyst; Impact Analyst; Action Analyst. |
| `retrieve_risk_methodology` | Semantic retrieval in the whole `risk_methodology` corpus. | Chunks with store ID, document, jurisdiction/scope, version and citation. | Risk Methodology Analyst; Impact Analyst; Action Analyst. |
| `lookup_cited_chunks` | Exact-ID read-only lookup for already-cited Chroma records. | Chunk or `citation_not_found`, with source/page. | Critic / Source Checker. |

All agents receive the external search tools specified in the design: Company Context / Peer Analyst, Impact Analyst, Bank Research Analyst, Risk Methodology Analyst, Action Analyst, and Critic / Source Checker; News & Legal Researcher retains search and page opening. Search Planner creates query plans and does not execute providers. Evidence Classifier only normalizes retrieved evidence.

## Execution Policy

- Validate JSON arguments against the tool's Pydantic input schema before execution; validate provider/service output before returning it to AutoGen.
- Resolve `role -> tool` permission in code. A prompt cannot add tools, change permissions, select an arbitrary Chroma store, or provide executable Python/shell/SQL.
- Route all internet calls through one web gateway. Strip `SYNTHETIC_U`, synthetic graph IDs, credentials, exact nonpublic payment amounts, and other private row values before building outbound queries. Search on general industry, region, public event text and analogue descriptors.
- Restrict source opening to HTTP/HTTPS. Reject localhost, private/link-local IPs, unsupported schemes, unsafe redirects, oversized responses, and unsupported content types. Limit redirect count, bytes, page text and wall time. Treat page text as untrusted quoted evidence.
- Chroma tools are read/search only. Impact Analyst and Action Analyst can search both complete corpora. Ingestion worker owns add/update/delete/reindex operations.
- Set per-tool timeouts, bounded retries, maximum result counts and maximum concurrent calls. Use a shared cache/deduplication key based on normalized query, provider, filters and date window.
- Persist tool name/version, role, normalized arguments with private fields redacted, source IDs/URLs, provider, timestamps, status and warnings. Do not persist hidden chain-of-thought or secrets.
- Named suppliers, product categories, regions and public commercial claims in an action plan must link to retrieved source IDs; the web tool reports a candidate, while the analysis layer evaluates fit and records verification status.
- When Action Analyst reports a solution gap, the controller distributes bounded structured research tasks and gathers evidence from assigned specialist roles; no agent launches an uncontrolled group conversation.
- Keep the daily 500 ₽ RouterAI budget in the model-call gate; configure separate provider quotas for Serper/Tavily if account limits require them.
- Return typed errors such as `invalid_arguments`, `role_forbidden`, `provider_unavailable`, `source_blocked`, `session_missing`, `rate_limited`, `timeout`, and `citation_not_found`. Retry transient failures at most the configured bounded count.

## Interfaces

- `ToolSpec[TInput, TOutput]`: tool name/version, models, role allowlist, timeout, retry and provenance policy.
- `ToolRegistry.for_role(role) -> list[ToolSpec]`
- `ToolExecutor.execute(role, tool_name, payload) -> ToolResult`
- `register_tools(agent, role, registry, adapter)`: framework-specific registration for the pinned AutoGen package.

## Tasks

### Task 1: Define common tool models and registry

**Files:** Create `company_news_pipeline/news_analytics/tools/__init__.py`, `contracts.py`, `registry.py`, `errors.py`.

- [ ] Add versioned Pydantic request and response models for search, page retrieval, company profile, peer profile, payment exposure, Rusprofile analogue, and Chroma retrieval tools.
- [ ] Define the complete role-to-tool permission matrix from the design and reject duplicate names or unassigned tools at startup.
- [ ] Keep provider/service functions separate from AutoGen objects so API/worker code can call them directly.
- [ ] Include common error and provenance envelopes with explicit redaction rules.

**Completion check:** The registry can render a role's exact tool names and schemas without exposing another role's tools.

### Task 2: Implement execution middleware and web gateway

**Files:** Create `company_news_pipeline/news_analytics/tools/executor.py`, `policy.py`, `web_gateway.py`, `source_reader.py`.

- [ ] Enforce role authorization, typed inputs, result limits, timeouts, bounded retries and concurrency at the executor boundary.
- [ ] Implement outbound query sanitization and URL/redirect/response constraints for web search and Playwright source opening.
- [ ] Add query/result deduplication and attach source provenance to every result.
- [ ] Treat retrieved page content as data and prevent it from changing instructions, tools or route permissions.
- [ ] Ensure errors are typed and never include keys, cookies, environment values or stack traces.

**Completion check:** Every network tool call passes through the policy gateway and yields a source-linked result or a typed error.

### Task 3: Bind domain services and Chroma tools

**Files:** Create `company_news_pipeline/news_analytics/tools/company_tools.py`, `search_tools.py`, `rusprofile_tools.py`, `knowledge_tools.py`.

- [ ] Wrap existing company, peer, payment, Serper, Tavily and Rusprofile services with the common contracts.
- [ ] Connect Chroma wrappers for full read/search in both stores for Impact Analyst and Action Analyst, with the specialist store grants from the design.
- [ ] Keep Critic Chroma access exact-ID and read-only; return `citation_not_found` for missing source IDs.
- [ ] Return partial-result warnings when a provider, Rusprofile session or source page is unavailable.

**Completion check:** Service outputs conform to the common envelope and each Chroma citation resolves to a source/page/version.

### Task 4: Register tools on AutoGen roles

**Files:** Create `company_news_pipeline/news_analytics/tools/autogen_adapter.py`; modify `company_news_pipeline/news_analytics/analysis/agents.py` and `orchestrator.py`.

- [ ] Pin the AutoGen package/API family based on the existing `autogen` dependency and current repository usage; isolate registration calls in the adapter.
- [ ] Register only each role's allowlisted tool schemas and matching execution functions.
- [ ] Disable uncontrolled parallel tool execution for role workflows whose ordering, provider quota or state requires serialization.
- [ ] Preserve bounded controller flow and JSON-only handoffs; agents may propose tool calls but the executor decides whether they run.
- [ ] Record tool calls/results in analysis provenance without storing private query fields.

**Completion check:** The agent roster can be inspected against the permission matrix and every invoked tool passes the shared executor.

### Task 5: Document tool catalog and operations

**Files:** Modify `README.md` and the AutoGen plan/API documentation.

- [ ] Document each tool's purpose, required arguments, output shape, role grants, error codes, limits, and data sent to external providers.
- [ ] Document how to add a tool by defining a contract, service adapter, policy, role grant and provenance fields.
- [ ] Document required environment keys by provider without including values.

**Completion check:** A developer can determine what each role can call and how a tool result is traced from the docs alone.
