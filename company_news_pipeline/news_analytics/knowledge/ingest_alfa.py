"""Page-aware, hash-versioned indexing for the supplied Alpha PDFs."""

from __future__ import annotations

import hashlib
import json
import re
import argparse
from pathlib import Path
from typing import Any

from .config import mark_store_ready, open_store
from .embeddings import embed_passages


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _chunks(text: str, size: int = 1200, overlap: int = 180) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    result = []
    start = 0
    while start < len(normalized):
        end = min(start + size, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(". ", start + size // 2, end)
            if boundary > start:
                end = boundary + 1
        result.append(normalized[start:end].strip())
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)
    return result


def ingest_alfa_folder(source_dir: str | Path, manifest_path: str | Path) -> dict[str, Any]:
    """Index active manifest entries and retire stale chunks after upsert succeeds."""

    source_dir = Path(source_dir).resolve()
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _, collection = open_store("alfa_research", create=True)
    reports = []

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("Install the pinned PyMuPDF dependency before Alpha ingestion") from exc

    for item in manifest.get("documents", []):
        if not item.get("active", True):
            continue
        path = (source_dir / Path(item["local_path"]).name).resolve()
        if source_dir not in path.parents or not path.is_file():
            reports.append({"document_id": item.get("document_id"), "status": "missing", "chunks": 0})
            continue
        file_hash = _sha256(path)
        new_ids: list[str] = []
        new_docs: list[str] = []
        new_metadatas: list[dict[str, Any]] = []
        covered_pages: list[int] = []
        ocr_pages: list[int] = []
        with fitz.open(path) as pdf:
            for page_number, page in enumerate(pdf, start=1):
                page_text = page.get_text("text") or ""
                if not page_text.strip():
                    ocr_pages.append(page_number)
                    continue
                blocks = [line.strip() for line in page_text.splitlines() if line.strip()]
                section_path = [line for line in blocks if line.isupper() and 4 <= len(line) <= 100][:4]
                for chunk_index, excerpt in enumerate(_chunks(page_text)):
                    chunk_id = hashlib.sha256(
                        f"{file_hash}:{page_number}:{chunk_index}".encode("utf-8")
                    ).hexdigest()
                    new_ids.append(chunk_id)
                    new_docs.append(excerpt)
                    new_metadatas.append({
                        "knowledge_store": "alfa_research",
                        "document_id": item.get("document_id") or file_hash[:24],
                        "title": item.get("title") or path.name,
                        "source_url": item.get("source_url") or item.get("source_url", ""),
                        "publication_date": str(item.get("publication_date") or ""),
                        "version": str(item.get("retrieval_date") or ""),
                        "content_hash": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                        "file_hash": file_hash,
                        "page_start": page_number,
                        "page_end": page_number,
                        "section_path": json.dumps(section_path, ensure_ascii=False),
                        "license_scope": str(item.get("license_scope") or "User-supplied local research corpus"),
                    })
                    covered_pages.append(page_number)
        if new_ids:
            embeddings = embed_passages(new_docs)
            collection.upsert(ids=new_ids, documents=new_docs, metadatas=new_metadatas, embeddings=embeddings)
            # Deletion happens only after the replacement chunks were indexed.
            stale = collection.get(where={"document_id": item.get("document_id") or file_hash[:24]})
            obsolete_ids = [
                chunk_id for chunk_id, metadata in zip(stale["ids"], stale["metadatas"] or [])
                if metadata.get("file_hash") != file_hash
            ]
            if obsolete_ids:
                collection.delete(ids=obsolete_ids)
        item.update({
            "sha256": file_hash,
            "status": "indexed" if new_ids else "ocr_required",
            "chunk_count": len(new_ids),
            "covered_pages": sorted(set(covered_pages)),
            "ocr_required_pages": ocr_pages,
        })
        reports.append({
            "document_id": item.get("document_id"), "path": path.as_posix(),
            "status": item["status"], "chunks": len(new_ids),
            "page_coverage": item["covered_pages"], "ocr_required_pages": ocr_pages,
        })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    total_chunks = sum(x["chunks"] for x in reports)
    mark_store_ready("alfa_research", indexed_chunks=total_chunks)
    return {"knowledge_store": "alfa_research", "files": reports, "chunk_count": total_chunks}


def main() -> None:
    parser = argparse.ArgumentParser(description="Index the local Alpha PDF corpus")
    repository_dir = Path(__file__).resolve().parents[3]
    parser.add_argument("--source-dir", default=str(repository_dir / "data/alfa_research"))
    parser.add_argument("--manifest", default=str(Path(__file__).with_name("sources.json")))
    args = parser.parse_args()
    print(json.dumps(ingest_alfa_folder(args.source_dir, args.manifest), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
