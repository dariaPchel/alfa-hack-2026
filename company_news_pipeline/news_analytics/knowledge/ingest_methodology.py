"""Ingest explicitly authorized local methodology excerpts into their own store."""

from __future__ import annotations

import hashlib
import json
import argparse
from pathlib import Path
from typing import Any

from .config import mark_store_ready, open_store
from .embeddings import embed_passages
from .ingest_alfa import _chunks


def ingest_methodology_sources(
    registry_path: str | Path,
    source_dir: str | Path,
) -> dict[str, Any]:
    """Index only registered local markdown/text excerpts; never scrape paywalled standards."""

    registry_path, source_dir = Path(registry_path), Path(source_dir)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    _, collection = open_store("risk_methodology", create=True)
    reports = []
    for source in registry.get("sources", []):
        if not source.get("active", True):
            reports.append({"document_id": source["document_id"], "status": "inactive", "chunks": 0})
            continue
        content_path = (source_dir / source["content_file"]).resolve()
        if source_dir.resolve() not in content_path.parents or not content_path.is_file():
            reports.append({"document_id": source["document_id"], "status": "source_text_missing", "chunks": 0})
            continue
        content = content_path.read_text(encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunks = _chunks(content)
        ids = [hashlib.sha256(f"{source['document_id']}:{digest}:{i}".encode()).hexdigest() for i in range(len(chunks))]
        metadata = [{
            "knowledge_store": "risk_methodology",
            "document_id": source["document_id"],
            "title": source["title"],
            "source_url": source["source_url"],
            "publication_date": str(source.get("version", "")),
            "version": str(source.get("version", "")),
            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "source_hash": digest,
            "section_path": "[]",
            "topic": source["topic"],
            "jurisdiction": source["jurisdiction"],
            "applicability": source["applicability"],
            "license_scope": source["license_scope"],
            "active": True,
        } for text in chunks]
        if ids:
            collection.upsert(ids=ids, documents=chunks, metadatas=metadata, embeddings=embed_passages(chunks))
            old = collection.get(where={"document_id": source["document_id"]})
            stale_ids = [
                chunk_id for chunk_id, item in zip(old["ids"], old["metadatas"] or [])
                if item.get("source_hash") != digest
            ]
            if stale_ids:
                collection.delete(ids=stale_ids)
        reports.append({"document_id": source["document_id"], "status": "indexed", "chunks": len(chunks), "sha256": digest})
    total_chunks = sum(item["chunks"] for item in reports)
    mark_store_ready("risk_methodology", indexed_chunks=total_chunks)
    return {"knowledge_store": "risk_methodology", "sources": reports, "chunk_count": total_chunks}


def main() -> None:
    parser = argparse.ArgumentParser(description="Index authorized local methodology excerpts")
    pipeline_dir = Path(__file__).resolve().parents[2]
    parser.add_argument("--registry", default=str(Path(__file__).with_name("methodology_sources.json")))
    parser.add_argument("--source-dir", default=str(pipeline_dir / "data" / "methodology_sources"))
    args = parser.parse_args()
    print(json.dumps(ingest_methodology_sources(args.registry, args.source_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
