"""Privacy-filtered web search gateway for all Analyst and Critic roles."""

from __future__ import annotations

import os
import hashlib
import threading
import time
import copy
from typing import Any

import requests

from .policy import sanitize_outbound_query


_CACHE_TTL_SECONDS = 300
_CACHE_MAX_ENTRIES = 128
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()


def search_web(query: str, provider: str = "serper", limit: int = 5) -> dict[str, Any]:
    query, warnings = sanitize_outbound_query(query)
    if not query:
        return {"status": "error", "error_code": "empty_after_redaction", "results": [], "warnings": warnings}
    limit = max(1, min(int(limit), 10))
    key_material = f"{provider.casefold()}\0{limit}\0{' '.join(query.casefold().split())}"
    cache_key = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and cached[0] > now:
            result = copy.deepcopy(cached[1])
            result["warnings"] = list(dict.fromkeys([*warnings, *result.get("warnings", [])]))
            return result
        _CACHE.pop(cache_key, None)
    try:
        if provider == "serper":
            key = os.getenv("SERPER_API_KEY")
            if not key:
                return {"status": "error", "error_code": "provider_unavailable", "results": [],
                        "warnings": warnings + ["SERPER_API_KEY is not configured"]}
            response = requests.post("https://google.serper.dev/search", json={"q": query, "num": limit},
                                     headers={"X-API-KEY": key, "Content-Type": "application/json"}, timeout=(5, 20))
            response.raise_for_status()
            raw = response.json().get("organic", [])
            results = [{"title": item.get("title"), "url": item.get("link"),
                        "snippet": item.get("snippet"), "position": item.get("position"),
                        "provider": "serper", "query": query} for item in raw[:limit]]
        elif provider == "tavily":
            key = os.getenv("TAVILY_API_KEY")
            if not key:
                return {"status": "error", "error_code": "provider_unavailable", "results": [],
                        "warnings": warnings + ["TAVILY_API_KEY is not configured"]}
            response = requests.post("https://api.tavily.com/search", json={"api_key": key, "query": query,
                                     "max_results": limit, "include_answer": False}, timeout=(5, 20))
            response.raise_for_status()
            raw = response.json().get("results", [])
            results = [{"title": item.get("title"), "url": item.get("url"),
                        "snippet": item.get("content"), "score": item.get("score"),
                        "provider": "tavily", "query": query} for item in raw[:limit]]
        else:
            return {"status": "error", "error_code": "invalid_provider", "results": [], "warnings": warnings}
        result = {"status": "success" if results else "partial", "results": results, "warnings": warnings,
                  "provider": provider, "query": query}
        if result["status"] != "error":
            with _CACHE_LOCK:
                if len(_CACHE) >= _CACHE_MAX_ENTRIES:
                    oldest = min(_CACHE, key=lambda item: _CACHE[item][0])
                    _CACHE.pop(oldest, None)
                _CACHE[cache_key] = (time.monotonic() + _CACHE_TTL_SECONDS, copy.deepcopy(result))
        return result
    except requests.Timeout:
        return {"status": "error", "error_code": "timeout", "results": [], "warnings": warnings}
    except (requests.RequestException, ValueError):
        return {"status": "error", "error_code": "provider_unavailable", "results": [], "warnings": warnings}
