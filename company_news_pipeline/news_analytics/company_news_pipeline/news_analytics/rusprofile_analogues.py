"""Rusprofile enrichment for anonymized analogue profiles."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable

from .models import CompanyProfile


def build_analogue_query(profile: CompanyProfile) -> str | None:
    """Build a public search phrase without exposing synthetic graph IDs."""

    size = " ".join(
        value for value in (profile.amount_workers_fns_gradation, profile.revenue_company) if value
    )
    pieces = [profile.mainokved_name, profile.org_type, profile.okfs_name, profile.region, size]
    query = " ".join(dict.fromkeys(str(value).strip() for value in pieces if value and str(value).strip()))
    return query or None


def _flatten_years(value: Any) -> set[str]:
    years: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if re.fullmatch(r"(?:19|20)\d{2}", str(key)):
                years.add(str(key))
            years.update(_flatten_years(nested))
    elif isinstance(value, list):
        for nested in value:
            years.update(_flatten_years(nested))
    return years


def _indicator_snippets(text: str, terms: tuple[str, ...], radius: int = 180) -> list[str]:
    snippets: list[str] = []
    folded = text.casefold()
    for term in terms:
        start = 0
        while (index := folded.find(term.casefold(), start)) >= 0:
            snippet = " ".join(text[max(0, index - radius // 2): index + radius // 2].split())
            if snippet and snippet not in snippets:
                snippets.append(snippet)
            start = index + len(term)
    return snippets


def _score_candidate(profile: CompanyProfile, candidate: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    search = candidate.get("search_result") or {}
    page = candidate.get("profile_page") or {}
    text = " ".join(str(part or "") for part in (candidate.get("name"), page.get("text"), search.get("okved_descr")))
    features: dict[str, float | None] = {}
    industry = profile.mainokved_name
    if industry:
        features["industry_text"] = 1.0 if industry.casefold() in text.casefold() else None
    candidate_region = candidate.get("region") or search.get("address") or ""
    if profile.region and candidate_region:
        features["region"] = 1.0 if str(profile.region).casefold() in str(candidate_region).casefold() else 0.0
    legal = " ".join(str(value or "") for value in (candidate.get("org_type"), search.get("ref_type")))
    if profile.org_type and legal:
        features["ownership_type"] = 1.0 if str(profile.org_type).casefold() in legal.casefold() else None
    available = [value for value in features.values() if value is not None]
    return (sum(available) / len(available) if available else 0.0), features


def enrich_rusprofile_analogues(
    profile: CompanyProfile,
    *,
    search: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Search Rusprofile using public attributes and return analogue-only facts.

    The current legacy parser returns the first search result plus its complete
    profile. The response preserves that limitation and never treats returned
    facts as facts about the selected synthetic company.
    """

    query = build_analogue_query(profile)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    if not query:
        return {
            "status": "unavailable", "query": None, "retrieved_at": retrieved_at,
            "analogues": [], "warning": "No public industry, legal-form, or region attributes are available.",
        }

    if search is None:
        from PARSING.rusprofile import parse_rusprofile
        search = parse_rusprofile
    result = search(query)
    if not isinstance(result, dict) or result.get("error"):
        return {
            "status": "unavailable", "query": query, "retrieved_at": retrieved_at, "analogues": [],
            "warning": (result.get("error") if isinstance(result, dict) else None)
            or "Rusprofile returned an unexpected response.",
        }

    profile_page = result.get("profile_page") or {}
    raw_text = str(profile_page.get("text") or result.get("raw_text_content") or "")
    score, matched_features = _score_candidate(profile, result)
    company_id = str(profile_page.get("company_id") or result.get("company_id") or "")
    url = profile_page.get("url") or result.get("url") or (
        f"https://www.rusprofile.ru/id/{company_id}" if company_id else None
    )
    financial = result.get("finance") or {}
    candidate = {
        "rusprofile_id": company_id or None,
        "name": result.get("name") or profile_page.get("name"),
        "url": url,
        "query": query,
        "retrieved_at": retrieved_at,
        "analogue_similarity_score": score,
        "matched_features": matched_features,
        "available_financial_years": sorted(_flatten_years(financial)),
        "material_fact_indicators": _indicator_snippets(
            raw_text, ("существенных фактах", "существенный факт", "corporate material fact")
        ),
        "court_indicators": _indicator_snippets(raw_text, ("арбитраж", "судебн", "иск", "дело №", "court", "lawsuit")),
        "financial_data": financial,
        "search_result": result.get("search_result") or {},
        "source": "Rusprofile public analogue; not a fact about the synthetic target",
    }
    return {
        "status": "partial" if not candidate["rusprofile_id"] else "available",
        "query": query,
        "retrieved_at": retrieved_at,
        "analogues": [candidate],
        "warning": "The legacy Rusprofile parser currently yields one leading match per query; verify analogue relevance before using its facts.",
    }
