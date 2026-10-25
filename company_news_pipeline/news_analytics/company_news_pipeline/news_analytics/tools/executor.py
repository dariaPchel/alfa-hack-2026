"""Bounded, role-checked execution boundary for registered tools."""

from __future__ import annotations

import time
import uuid
import hashlib
import json
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any

from .contracts import ToolResult
from .registry import ToolRegistry
from ..db import Database


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, *, max_workers: int = 8, db: Database | None = None) -> None:
        self.registry = registry
        self.db = db
        self._pool = ThreadPoolExecutor(max_workers=max(1, min(max_workers, 16)), thread_name_prefix="agent-tool")

    def _audit(self, result: ToolResult, role: str, tool_name: str, payload: dict[str, Any], started: float) -> ToolResult:
        if self.db is None:
            return result
        spec = self.registry.get(tool_name)
        request_material = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
        arguments_hash = hashlib.sha256(request_material.encode("utf-8")).hexdigest()
        sources = []
        for item in result.sources[:50]:
            if not isinstance(item, dict):
                continue
            source = {key: item[key] for key in ("source_id", "chunk_id", "document_id", "title", "page") if key in item}
            url = item.get("url")
            if isinstance(url, str):
                from urllib.parse import urlsplit
                source["host"] = urlsplit(url).hostname
                source["url_sha256"] = hashlib.sha256(url.encode("utf-8")).hexdigest()
            if source:
                sources.append(source)
        data = result.data
        provider = data.get("provider") if isinstance(data, dict) else None
        try:
            with self.db.connect() as connection:
                connection.execute(
                    """INSERT OR REPLACE INTO agent_tool_audit
                       (request_id, role, tool_name, tool_version, arguments_sha256, provider,
                        source_refs_json, status, error_code, elapsed_ms, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (result.request_id, role, tool_name, spec.version if spec else None, arguments_hash,
                     provider, json.dumps(sources, ensure_ascii=False), result.status, result.error_code,
                     round((time.monotonic() - started) * 1000), datetime.now(timezone.utc).isoformat()),
                )
        except Exception:
            # Surface missing audit persistence without leaking database internals.
            result.warnings.append("Tool audit persistence unavailable")
            if result.status == "success":
                result.status = "partial"
        return result

    def execute(self, role: str, tool_name: str, payload: dict[str, Any]) -> ToolResult:
        request_id = uuid.uuid4().hex
        started = time.monotonic()
        spec = self.registry.get(tool_name)
        if spec is None:
            return self._audit(self._error(request_id, started, "tool_not_found", "Tool is not registered"), role, tool_name, payload, started)
        if role not in spec.roles:
            return self._audit(self._error(request_id, started, "role_forbidden", "This role cannot call the requested tool"), role, tool_name, payload, started)
        try:
            request = spec.request_model.model_validate(payload)
        except Exception:
            return self._audit(self._error(request_id, started, "invalid_arguments", "Arguments did not match the tool schema"), role, tool_name, payload, started)

        attempts = spec.retries + 1
        for attempt in range(attempts):
            future = self._pool.submit(spec.handler, role=role, **request.model_dump())
            try:
                data = future.result(timeout=spec.timeout_seconds)
                if spec.response_model is not None:
                    data = spec.response_model.model_validate(data).model_dump(mode="json")
                elapsed = round((time.monotonic() - started) * 1000)
                if isinstance(data, ToolResult):
                    data.request_id = request_id
                    data.elapsed_ms = elapsed
                    return self._audit(data, role, tool_name, payload, started)
                status = "partial" if isinstance(data, dict) and data.get("warnings") else "success"
                result = ToolResult(status=status, data=data, request_id=request_id, elapsed_ms=elapsed)
                return self._audit(result, role, tool_name, payload, started)
            except FutureTimeout:
                future.cancel()
                if attempt + 1 == attempts:
                    return self._audit(self._error(request_id, started, "timeout", "Tool exceeded its time limit"), role, tool_name, payload, started)
            except PermissionError:
                return self._audit(self._error(request_id, started, "role_forbidden", "This role cannot access the requested resource"), role, tool_name, payload, started)
            except ValueError:
                return self._audit(self._error(request_id, started, "invalid_arguments", "Tool rejected the supplied arguments"), role, tool_name, payload, started)
            except Exception:
                if attempt + 1 == attempts:
                    return self._audit(self._error(request_id, started, "tool_failed", "Tool execution failed"), role, tool_name, payload, started)
        return self._audit(self._error(request_id, started, "tool_failed", "Tool execution failed"), role, tool_name, payload, started)

    @staticmethod
    def _error(request_id: str, started: float, error_code: str, message: str) -> ToolResult:
        return ToolResult(status="error", error_code=error_code, warnings=[message], request_id=request_id,
                          elapsed_ms=max(0, round((time.monotonic() - started) * 1000)))
