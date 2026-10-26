"""Export supplied Alfa PDF pages into the Go bank_research JSONL import format."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path


def chunks(text: str, size: int = 1200, overlap: int = 150) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    result = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        result.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return result


def ocr_page(pdf_path: Path, page_number: int) -> str:
    with tempfile.TemporaryDirectory() as directory:
        prefix = Path(directory) / "page"
        subprocess.run(["pdftoppm", "-f", str(page_number), "-l", str(page_number),
                        "-singlefile", "-r", "150", "-png", str(pdf_path), str(prefix)],
                       check=True, stdout=subprocess.DEVNULL, timeout=120)
        result = subprocess.run(["tesseract", str(prefix) + ".png", "stdout", "-l", "rus+eng"],
                                check=True, capture_output=True, text=True, timeout=120)
        return result.stdout


def export(source_dir: Path, manifest_path: Path, output: Path) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = [item for item in manifest.get("documents", []) if item.get("active", True)]
    if not source_dir.exists():
        raise RuntimeError(f"Supplied Alfa PDF directory does not exist: {source_dir}")
    missing = []
    for item in documents:
        candidate = source_dir / Path(item["local_path"]).name
        try:
            present = candidate.is_file()
        except OSError:
            present = False
        if not present:
            missing.append(item.get("local_path"))
    if missing:
        raise RuntimeError("Missing supplied Alfa PDF files: " + ", ".join(missing))
    digest_check = hashlib.sha256()
    for item in documents:
        pdf_path = source_dir / Path(item["local_path"]).name
        digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        if item.get("sha256") and item["sha256"] != digest:
            raise RuntimeError(f"SHA-256 mismatch: {pdf_path.name}")
        digest_check.update(digest.encode())
    stamp_value = digest_check.hexdigest()
    stamp_path = output.with_suffix(output.suffix + ".stamp")
    if output.is_file() and output.stat().st_size > 0 and stamp_path.is_file() \
            and stamp_path.read_text(encoding="utf-8") == stamp_value:
        return sum(1 for _ in output.open(encoding="utf-8"))
    try:
        import fitz
    except ImportError:
        fitz = None
    if fitz is None:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("Install PyMuPDF or pypdf to extract the supplied PDFs") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    count = 0
    with temporary.open("w", encoding="utf-8") as stream:
        for item in documents:
            pdf_path = source_dir / Path(item["local_path"]).name
            digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            source_url = item.get("source_url", "")
            if not source_url.startswith(("https://", "http://")):
                raise RuntimeError(f"Missing source URL: {pdf_path.name}")
            if fitz is not None:
                with fitz.open(pdf_path) as pdf:
                    pages = [(number, page.get_text("text") or "")
                             for number, page in enumerate(pdf, start=1)]
            else:
                pdf = PdfReader(str(pdf_path))
                pages = [(number, page.extract_text() or "")
                         for number, page in enumerate(pdf.pages, start=1)]
            for page_number, page_text in pages:
                if not page_text.strip():
                    page_text = ocr_page(pdf_path, page_number)
                for index, text in enumerate(chunks(page_text)):
                    record = {
                        "id": f"{digest[:16]}-{page_number}-{index}",
                        "title": item.get("title") or pdf_path.name,
                        "url": source_url,
                        "page": page_number,
                        "content": text,
                    }
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1
    if count == 0:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("No text extracted from the supplied Alfa PDFs")
    temporary.replace(output)
    stamp_path.write_text(stamp_value, encoding="utf-8")
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path("research/sources.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(f"Exported {export(args.source_dir, args.manifest, args.output)} fragments")


if __name__ == "__main__":
    main()
