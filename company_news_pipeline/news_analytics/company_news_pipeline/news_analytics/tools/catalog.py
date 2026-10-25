"""Bind domain services into the role-scoped common tool registry."""

from __future__ import annotations

from typing import Any

from ..company_profiles import get_company_profile
from ..db import Database
from ..payment_network import get_counterparty_industries
from ..peer_matching import find_peers
from ..rusprofile_analogues import enrich_rusprofile_analogues
from ..search.refresh import get_company_news
from ..search.serper_news import search_serper_news
from .contracts import (
    CitationLookupRequest, CompanyIdRequest, KnowledgeSearchRequest, NewsSearchRequest,
    OpenSourceRequest, PaymentExposureRequest, PeerRequest, RusprofileProfileRequest,
    RusprofileSearchRequest, ToolResult, WebSearchRequest,
)
from .registry import ToolRegistry, ToolSpec
from .source_reader import open_source_page
from .web_gateway import search_web
from ..knowledge.tools import citation_lookup, knowledge_search


ROLE_COMPANY = frozenset({"Company Context / Peer Analyst", "controller"})
ROLE_ANALYSTS = frozenset({
    "Company Context / Peer Analyst", "Impact Analyst", "Bank Research Analyst",
    "Risk Methodology Analyst", "Action Analyst", "Critic / Source Checker",
})
ROLE_NEWS = frozenset({"News & Legal Researcher", "Impact Analyst", "Bank Research Analyst",
                       "Risk Methodology Analyst", "Action Analyst", "Critic / Source Checker"})
ROLE_KNOWLEDGE = frozenset({"Bank Research Analyst", "Risk Methodology Analyst", "Impact Analyst", "Action Analyst"})
ROLE_CITATIONS = frozenset({"Critic / Source Checker", "Impact Analyst", "Action Analyst"})


def _tool_result(data: Any, *, status: str = "success", sources: list[dict[str, Any]] | None = None,
                 warnings: list[str] | None = None, error_code: str | None = None) -> ToolResult:
    return ToolResult(status=status, data=data, sources=sources or [], warnings=warnings or [],
                      error_code=error_code, request_id="pending", elapsed_ms=0)


def build_default_registry(db: Database) -> ToolRegistry:
    registry = ToolRegistry()

    def company_profile(synthetic_id: str, role: str):
        profile = get_company_profile(synthetic_id, db)
        if profile is None:
            return _tool_result(None, status="error", error_code="company_not_found")
        return _tool_result(profile.model_dump(mode="json"), warnings=profile.source_metadata.get("missing_optional_fields", []))

    def peer_companies(synthetic_id: str, limit: int = 10, role: str = ""):
        peers = find_peers(synthetic_id, db, limit=limit)
        return _tool_result([item.model_dump(mode="json") for item in peers])

    def payment_exposure(synthetic_id: str, limit: int = 10, role: str = ""):
        values = get_counterparty_industries(synthetic_id, db, limit=limit)
        return _tool_result([item.model_dump(mode="json") for item in values])

    def rusprofile_search(synthetic_id: str, role: str = ""):
        profile = get_company_profile(synthetic_id, db)
        if profile is None:
            return _tool_result(None, status="error", error_code="company_not_found")
        result = enrich_rusprofile_analogues(profile)
        warnings = [result["warning"]] if result.get("warning") else []
        status = {"available": "success", "partial": "partial", "unavailable": "error"}.get(result.get("status"), "partial")
        return _tool_result(result, status=status, warnings=warnings,
                            error_code="session_missing" if status == "error" and "session" in " ".join(warnings).casefold() else None,
                            sources=[{"url": item.get("url"), "source": "rusprofile_analogue"}
                                     for item in result.get("analogues", []) if item.get("url")])

    def rusprofile_profile(rusprofile_id: str, role: str = ""):
        from PARSING.rusprofile import parse_rusprofile
        result = parse_rusprofile(rusprofile_id)
        if result.get("error"):
            return _tool_result(result, status="error", error_code="session_missing" if "session" in result["error"].lower() else "provider_unavailable",
                                warnings=[result["error"]])
        return _tool_result(result, sources=[{"url": result.get("url"), "source": "rusprofile"}] if result.get("url") else [])

    def news_search(synthetic_id: str, query: str, window: str = "24h", limit: int = 10, role: str = ""):
        from .policy import sanitize_outbound_query
        public_query, warnings = sanitize_outbound_query(query)
        result = search_serper_news(public_query, max_results=limit, time_filter=window)
        status = "error" if result.error_code else "partial" if result.warning else "success"
        return _tool_result(result.model_dump(mode="json"), status=status, warnings=warnings + ([result.warning] if result.warning else []),
                            error_code=result.error_code,
                            sources=[{"url": event.url, "title": event.title} for event in result.results])

    def web_search(query: str, provider: str = "serper", limit: int = 5, role: str = ""):
        result = search_web(query, provider=provider, limit=limit)
        status = result.get("status", "error")
        return _tool_result(result, status=status, warnings=result.get("warnings", []),
                            error_code=result.get("error_code"), sources=result.get("results", []))

    def source_open(url: str, render_js: bool = False, role: str = ""):
        result = open_source_page(url, render_js=render_js)
        status = "error" if result.get("status") in {"blocked", "error"} else result.get("status", "error")
        return _tool_result(result, status=status,
                            warnings=result.get("warnings", []), error_code=result.get("error_code"),
                            sources=[{"url": result.get("url")} ] if result.get("url") else [])

    def alfa_search(query: str, topic: str | None = None, limit: int = 5, role: str = ""):
        chunks = knowledge_search(role, "alfa_research", query, limit=limit)
        return _tool_result([item.model_dump(mode="json") for item in chunks], sources=[{"chunk_id": x.chunk_id} for x in chunks])

    def methodology_search(query: str, topic: str | None = None, limit: int = 5, role: str = ""):
        if topic is None:
            return _tool_result(None, status="error", error_code="invalid_arguments")
        chunks = knowledge_search(role, "risk_methodology", query, topic=topic, limit=limit)
        return _tool_result([item.model_dump(mode="json") for item in chunks], sources=[{"chunk_id": x.chunk_id} for x in chunks])

    def citation_lookup_tool(store: str, chunk_ids: list[str], role: str = ""):
        result = citation_lookup(role, store, chunk_ids)
        missing = result["citation_not_found"]
        return _tool_result(result, status="partial" if missing else "success",
                            error_code="citation_not_found" if missing else None,
                            sources=[{"chunk_id": item["chunk_id"]} for item in result["chunks"]])

    specs = [
        ToolSpec("get_company_profile", "1.0", "Read one synthetic company profile", CompanyIdRequest, None, company_profile, ROLE_COMPANY),
        ToolSpec("find_peer_companies", "1.0", "Rank deterministic synthetic analogues", PeerRequest, None, peer_companies, ROLE_COMPANY),
        ToolSpec("get_industry_payment_exposure", "1.0", "Read payer/beneficiary industry exposures", PaymentExposureRequest, None, payment_exposure, ROLE_COMPANY | {"Impact Analyst", "Action Analyst"}),
        ToolSpec("search_rusprofile_analogues", "1.0", "Search Rusprofile using public profile descriptors", RusprofileSearchRequest, None, rusprofile_search, ROLE_COMPANY | {"Impact Analyst", "Action Analyst"}, 45),
        ToolSpec("get_rusprofile_analogue_profile", "1.0", "Retrieve one public Rusprofile analogue profile", RusprofileProfileRequest, None, rusprofile_profile, ROLE_COMPANY | {"Impact Analyst", "Action Analyst"}, 45),
        ToolSpec("search_news", "1.0", "Search a company's public news window", NewsSearchRequest, None, news_search, ROLE_NEWS, 30),
        ToolSpec("search_web", "1.0", "Search public web context", WebSearchRequest, None, web_search, ROLE_ANALYSTS, 25),
        ToolSpec("open_source_page", "1.0", "Open a bounded public source page", OpenSourceRequest, None, source_open, ROLE_ANALYSTS | {"News & Legal Researcher"}, 25),
        ToolSpec("retrieve_alfa_research", "1.0", "Search the Alpha research collection", KnowledgeSearchRequest, None, alfa_search, ROLE_KNOWLEDGE),
        ToolSpec("retrieve_risk_methodology", "1.0", "Search the risk methodology collection", KnowledgeSearchRequest, None, methodology_search, ROLE_KNOWLEDGE),
        ToolSpec("lookup_cited_chunks", "1.0", "Verify exact Chroma citation IDs", CitationLookupRequest, None, citation_lookup_tool, ROLE_CITATIONS),
    ]
    for spec in specs:
        registry.register(spec)
    return registry
