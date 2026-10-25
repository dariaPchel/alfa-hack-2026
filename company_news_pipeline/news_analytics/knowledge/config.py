"""Configuration and safe access to two physically separate Chroma stores."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal


StoreName = Literal["alfa_research", "risk_methodology"]
EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
EMBEDDING_DIMENSIONS = 1024
DEFAULT_PATHS = {
    "alfa_research": Path("data/vectorstores/alfa_research"),
    "risk_methodology": Path("data/vectorstores/risk_methodology"),
}


class KnowledgeStoreUnavailable(RuntimeError):
    """Raised when an existing knowledge store cannot be opened safely."""


def store_path(name: StoreName) -> Path:
    env_name = "NEWS_ANALYTICS_CHROMA_" + name.upper()
    return Path(os.getenv(env_name, str(DEFAULT_PATHS[name]))).expanduser()


def open_store(name: StoreName, *, create: bool = False):
    """Open only the requested collection; searches never create empty stores."""

    path = store_path(name)
    host = os.getenv(f"NEWS_ANALYTICS_CHROMA_{name.upper()}_HOST")
    if not create and not host and not (path / "chroma.sqlite3").is_file():
        raise KnowledgeStoreUnavailable(f"Knowledge store '{name}' is missing at {path}")
    try:
        import chromadb

        if host:
            port = int(os.getenv(f"NEWS_ANALYTICS_CHROMA_{name.upper()}_PORT", "8000"))
            ssl = os.getenv(f"NEWS_ANALYTICS_CHROMA_{name.upper()}_SSL", "false").casefold() == "true"
            client = chromadb.HttpClient(host=host, port=port, ssl=ssl)
        else:
            client = chromadb.PersistentClient(path=str(path))
        if create:
            collection = client.get_or_create_collection(name=name, metadata={
                "hnsw:space": "cosine", "embedding_model": EMBEDDING_MODEL,
                "embedding_dimensions": EMBEDDING_DIMENSIONS,
            })
            collection_metadata = collection.metadata or {}
            if collection.count() and (
                collection_metadata.get("embedding_model") != EMBEDDING_MODEL
                or collection_metadata.get("embedding_dimensions") != EMBEDDING_DIMENSIONS
            ):
                raise KnowledgeStoreUnavailable(
                    f"Knowledge store '{name}' uses another embedding model; reindex it into a clean store"
                )
        else:
            collection = client.get_collection(name=name)
            if not collection.metadata or not collection.metadata.get("ingestion_ready"):
                raise KnowledgeStoreUnavailable(f"Knowledge store '{name}' has no completed ingestion marker")
            if (collection.metadata.get("embedding_model") != EMBEDDING_MODEL
                    or collection.metadata.get("embedding_dimensions") != EMBEDDING_DIMENSIONS):
                raise KnowledgeStoreUnavailable(
                    f"Knowledge store '{name}' uses another embedding model; reindex it into a clean store"
                )
    except KnowledgeStoreUnavailable:
        raise
    except Exception as exc:
        raise KnowledgeStoreUnavailable(f"Could not open knowledge store '{name}': {exc}") from exc
    return client, collection


def mark_store_ready(name: StoreName, *, indexed_chunks: int) -> None:
    """Mark the store available only after a successful nonempty ingestion."""

    if indexed_chunks <= 0:
        return
    from datetime import datetime, timezone

    _, collection = open_store(name, create=True)
    metadata = dict(collection.metadata or {})
    metadata.update({"ingestion_ready": True, "indexed_chunks": indexed_chunks,
                     "indexed_at": datetime.now(timezone.utc).isoformat(),
                     "embedding_model": EMBEDDING_MODEL,
                     "embedding_dimensions": EMBEDDING_DIMENSIONS})
    collection.modify(metadata=metadata)


def store_status(name: StoreName) -> dict[str, str | int | bool]:
    """Report counts without provisioning a missing database or collection."""

    try:
        _, collection = open_store(name)
    except KnowledgeStoreUnavailable as exc:
        return {"available": False, "path": str(store_path(name)), "error": str(exc), "count": 0}
    return {"available": True, "path": str(store_path(name)), "count": collection.count()}
