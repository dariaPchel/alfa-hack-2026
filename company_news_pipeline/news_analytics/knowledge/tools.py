"""Role-enforced server-side knowledge tools; raw Chroma clients stay private."""

from __future__ import annotations

from typing import Any

from .retrieval import lookup_cited_chunks, retrieve_alfa, retrieve_methodology


SEARCH_ACCESS = {
    "Bank Research Analyst": {"alfa_research"},
    "Risk Methodology Analyst": {"risk_methodology"},
    "Impact Analyst": {"alfa_research", "risk_methodology"},
    "Action Analyst": {"alfa_research", "risk_methodology"},
}
LOOKUP_ACCESS = {
    **SEARCH_ACCESS,
    "Critic / Source Checker": {"alfa_research", "risk_methodology"},
}


def knowledge_search(role: str, store: str, query: str, *, topic: str | None = None, limit: int = 5):
    allowed = SEARCH_ACCESS.get(role, set())
    if store not in allowed:
        raise PermissionError(f"Role {role!r} cannot search {store!r}")
    if store == "alfa_research":
        return retrieve_alfa(query, limit=limit)
    if store == "risk_methodology":
        if topic is None:
            raise ValueError("A methodology topic is required")
        return retrieve_methodology(query, topic, limit=limit)
    raise ValueError("Unknown knowledge store")


def citation_lookup(role: str, store: str, chunk_ids: list[str]) -> dict[str, Any]:
    if store not in LOOKUP_ACCESS.get(role, set()):
        raise PermissionError(f"Role {role!r} cannot look up citations in {store!r}")
    chunks = lookup_cited_chunks(store, chunk_ids)
    found = {chunk.chunk_id for chunk in chunks}
    return {
        "chunks": [chunk.model_dump(mode="json") for chunk in chunks],
        "citation_not_found": sorted(set(chunk_ids) - found),
    }
