"""Safe extraction and local folder synchronization for the Alpha corpus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


DRIVE_FOLDER_URL = "https://drive.google.com/drive/folders/15xZTLF1lZ65p6o5xpNA_fRbxjoV-UlG1"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def extract_archive(archive_path: str | Path, target_dir: str | Path) -> dict[str, object]:
    """Extract PDF entries only; reject traversal and avoid overwriting conflicts."""

    archive_path, target_dir = Path(archive_path), Path(target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    extracted, duplicates, unreadable = [], [], []
    with ZipFile(archive_path) as archive:
        for item in archive.infolist():
            member = PurePosixPath(item.filename)
            if item.is_dir() or member.suffix.casefold() != ".pdf":
                continue
            if member.is_absolute() or ".." in member.parts:
                unreadable.append({"entry": item.filename, "reason": "unsafe path"})
                continue
            destination = (target_dir / member.name).resolve()
            if target_dir not in destination.parents:
                unreadable.append({"entry": item.filename, "reason": "path escaped target"})
                continue
            try:
                payload = archive.read(item)
            except Exception as exc:
                unreadable.append({"entry": item.filename, "reason": str(exc)})
                continue
            if destination.exists():
                if _sha256_bytes(destination.read_bytes()) == _sha256_bytes(payload):
                    duplicates.append({"entry": item.filename, "path": str(destination)})
                    continue
                unreadable.append({"entry": item.filename, "reason": "destination exists with different content"})
                continue
            destination.write_bytes(payload)
            extracted.append({"entry": item.filename, "path": str(destination), "sha256": _sha256_bytes(payload)})
    return {"extracted": extracted, "unchanged": duplicates, "unreadable": unreadable,
            "drive_sync": "not attempted; configure authenticated Drive API access to refresh the shared folder"}


def sync_local_folder(source_dir: str | Path, manifest_path: str | Path) -> dict[str, object]:
    """Mark unchanged, changed, missing and inaccessible documents from a local mirror."""

    source_dir, manifest_path = Path(source_dir).resolve(), Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    states = {"changed": [], "unchanged": [], "missing": [], "inaccessible": []}
    for document in manifest.get("documents", []):
        name = Path(document.get("local_path", "")).name
        path = (source_dir / name).resolve()
        if source_dir not in path.parents:
            states["inaccessible"].append(name)
            continue
        if not path.is_file():
            states["missing"].append(name)
            document["active"] = False
            document["status"] = "missing"
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            states["inaccessible"].append(name)
            continue
        if digest == document.get("sha256"):
            states["unchanged"].append(name)
        else:
            states["changed"].append(name)
            document["previous_sha256"] = document.get("sha256")
            document["sha256"] = digest
            document["status"] = "changed_pending_reindex"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return states
