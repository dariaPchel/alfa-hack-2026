"""Read-only, store-specific retrieval and citation lookup."""

from __future__ import annotations

import json
from typing import Any

from .config import KnowledgeStoreUnavailable, StoreName, open_store
from .embeddings import embed_queries
from .models import RetrievedChunk


def _decode_result(store: str, result: dict[str, Any]) -> list[RetrievedChunk]:
    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0] or []
    metadatas = result.get("metadatas", [[]])[0] or []
    distances = result.get("distances", [[]])[0] or []
    chunks = []
    for index, chunk_id in enumerate(ids):
        metadata = metadatas[index] or {}
        chunks.append(RetrievedChunk(
            chunk_id=chunk_id,
            knowledge_store=store,
            document_id=str(metadata.get("document_id", "")),
            title=str(metadata.get("title", "")),
            source_url=metadata.get("source_url") or None,
            publication_date=metadata.get("publication_date") or None,
            version=metadata.get("version") or None,
            content_hash=str(metadata.get("content_hash", "")),
            page_start=metadata.get("page_start"),
            page_end=metadata.get("page_end"),
            section_path=json.loads(metadata.get("section_path", "[]")),
            excerpt=documents[index] if index < len(documents) else "",
            jurisdiction=metadata.get("jurisdiction"),
            applicability=metadata.get("applicability"),
            license_scope=metadata.get("license_scope"),
            score=(1.0 - float(distances[index])) if index < len(distances) else None,
            metadata={key: value for key, value in metadata.items() if key not in {
                "knowledge_store", "document_id", "title", "source_url", "publication_date", "version",
                "content_hash", "page_start", "page_end", "section_path", "jurisdiction", "applicability", "license_scope"
            }},
        ))
    return chunks


def _where(filters: dict[str, Any] | None, *, allowed: set[str]) -> dict[str, Any] | None:
    if not filters:
        return None
    unknown = set(filters) - allowed
    if unknown:
        raise ValueError(f"Unsupported knowledge-store filters: {sorted(unknown)}")
    return {key: value for key, value in filters.items() if value is not None}


def _retrieve(store: StoreName, query: str, filters: dict[str, Any] | None, limit: int) -> list[RetrievedChunk]:
    if not query.strip():
        return []
    if limit < 1 or limit > 25:
        raise ValueError("limit must be between 1 and 25")
    _, collection = open_store(store, create=False)
    args: dict[str, Any] = {"query_embeddings": embed_queries([query]), "n_results": limit}
    if filters:
        args["where"] = filters
    return _decode_result(store, collection.query(**args))


def retrieve_alfa(query: str, filters: dict[str, Any] | None = None, limit: int = 5) -> list[RetrievedChunk]:
    allowed = {"document_id", "publication_date", "version"}
    return _retrieve("alfa_research", query, _where(filters, allowed=allowed), limit)


def retrieve_methodology(query: str, topic: str, limit: int = 5) -> list[RetrievedChunk]:
    if topic not in {"corporate_risk", "decision_analysis", "ai_governance", "model_governance"}:
        raise ValueError("Unknown methodology topic")
    return _retrieve("risk_methodology", query, {"topic": topic, "active": True}, limit)


def lookup_cited_chunks(store: str, chunk_ids: list[str]) -> list[RetrievedChunk]:
    """Perform exact-ID lookup only; broad search arguments are not accepted."""

    if store not in {"alfa_research", "risk_methodology"}:
        raise ValueError("Unknown knowledge store")
    if not chunk_ids:
        return []
    if len(chunk_ids) > 100:
        raise ValueError("At most 100 cited chunk IDs can be looked up at once")
    _, collection = open_store(store, create=False)  # type: ignore[arg-type]
    result = collection.get(ids=list(dict.fromkeys(chunk_ids)), include=["documents", "metadatas"])
    missing = sorted(set(chunk_ids) - set(result.get("ids", [])))
    if missing:
        # Existing citations are returned; the caller can compare requested IDs
        # with these and report citation_not_found for absent IDs.
        pass
    return _decode_result(str(store), {
        "ids": [result.get("ids", [])],
        "documents": [result.get("documents", [])],
        "metadatas": [result.get("metadatas", [])],
        "distances": [[]],
    })
