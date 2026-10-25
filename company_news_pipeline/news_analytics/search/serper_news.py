"""Rate-limited adapter for the Serper News vertical."""

from __future__ import annotations

import hashlib
import os
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import NewsEvent, ProviderSearchResult


SERPER_NEWS_URL = "https://google.serper.dev/news"
_RELATIVE_DATE = re.compile(r"(\d+)\s*(minute|hour|day|week|month|year)s?\s*ago", re.I)
_RU_RELATIVE_DATE = re.compile(r"(\d+)\s*(минут|час|дн|недел|месяц|год)", re.I)


def _canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def parse_provider_date(value: str | None, now: datetime | None = None) -> tuple[datetime | None, str]:
    if not value:
        return None, "undated"
    now = now or datetime.now(timezone.utc)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (result if result.tzinfo else result.replace(tzinfo=timezone.utc)), "parsed"
    except ValueError:
        pass
    try:
        result = parsedate_to_datetime(value)
        return (result if result.tzinfo else result.replace(tzinfo=timezone.utc)), "parsed"
    except (TypeError, ValueError, OverflowError):
        pass
    match = _RELATIVE_DATE.search(value)
    if match:
        count, unit = int(match.group(1)), match.group(2).lower()
        delta = {
            "minute": timedelta(minutes=count), "hour": timedelta(hours=count),
            "day": timedelta(days=count), "week": timedelta(weeks=count),
            "month": timedelta(days=30 * count), "year": timedelta(days=365 * count),
        }[unit]
        return now - delta, "parsed"
    match = _RU_RELATIVE_DATE.search(value.casefold())
    if match:
        count, unit = int(match.group(1)), match.group(2)
        if unit.startswith("минут"):
            delta = timedelta(minutes=count)
        elif unit.startswith("час"):
            delta = timedelta(hours=count)
        elif unit.startswith("дн"):
            delta = timedelta(days=count)
        elif unit.startswith("недел"):
            delta = timedelta(weeks=count)
        elif unit.startswith("месяц"):
            delta = timedelta(days=30 * count)
        else:
            delta = timedelta(days=365 * count)
        return now - delta, "parsed"
    return None, "unparseable"


def normalize_news_result(raw: dict[str, Any], retrieved_at: datetime, query: str) -> NewsEvent | None:
    title = str(raw.get("title") or "").strip()
    url = _canonical_url(str(raw.get("link") or raw.get("url") or ""))
    if not title or not url:
        return None
    provider_date = raw.get("date") or raw.get("publishedDate") or raw.get("published_at")
    published_at, date_status = parse_provider_date(str(provider_date) if provider_date else None, retrieved_at)
    identity = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return NewsEvent(
        event_id=identity,
        title=title,
        url=url,
        snippet=str(raw.get("snippet") or raw.get("description") or ""),
        publisher=raw.get("source") or raw.get("publisher"),
        provider_published_at=str(provider_date) if provider_date else None,
        published_at=published_at,
        date_status=date_status,
        image_url=raw.get("imageUrl") or raw.get("image_url"),
        provider_rank=raw.get("position"),
        query=query,
        retrieved_at=retrieved_at,
    )


def search_serper_news(query: str, max_results: int = 20, time_filter: str | None = None) -> ProviderSearchResult:
    retrieved_at = datetime.now(timezone.utc)
    if not query.strip():
        return ProviderSearchResult(query=query, provider="serper_news", retrieved_at=retrieved_at,
                                    error_code="invalid_query", warning="Query is empty")
    if not 1 <= max_results <= 20:
        raise ValueError("max_results must be between 1 and 20")
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        return ProviderSearchResult(query=query, provider="serper_news", retrieved_at=retrieved_at,
                                    error_code="provider_unavailable", warning="SERPER_API_KEY is not configured")

    date_range = {"24h": "qdr:d", "7d": "qdr:w", "90d": "qdr:m3"}
    if time_filter not in {None, *date_range}:
        raise ValueError("time_filter must be one of: 24h, 7d, 90d")
    payload: dict[str, Any] = {"q": query, "num": max_results}
    if time_filter:
        payload["tbs"] = date_range[time_filter]
    retry = Retry(total=2, connect=2, read=1, backoff_factor=0.4,
                  status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset({"POST"}),
                  raise_on_status=False)
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    started = time.monotonic()
    try:
        response = session.post(SERPER_NEWS_URL, json=payload,
                                headers={"X-API-KEY": api_key, "Content-Type": "application/json"}, timeout=(5, 20))
        if response.status_code == 429:
            return ProviderSearchResult(query=query, provider="serper_news", retrieved_at=retrieved_at,
                                        error_code="rate_limited", warning="Serper News rate limit reached")
        response.raise_for_status()
        data = response.json()
        results = [event for raw in data.get("news", [])[:max_results]
                   if (event := normalize_news_result(raw, retrieved_at, query)) is not None]
        return ProviderSearchResult(query=query, provider="serper_news", results=results,
                                    retrieved_at=retrieved_at,
                                    warning=None if results else "No usable news results returned",
                                    provider_metadata={"elapsed_ms": round((time.monotonic()-started)*1000),
                                                       "candidate_count": len(data.get("news", []))})
    except requests.Timeout:
        return ProviderSearchResult(query=query, provider="serper_news", retrieved_at=retrieved_at,
                                    error_code="timeout", warning="Serper News request timed out")
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return ProviderSearchResult(query=query, provider="serper_news", retrieved_at=retrieved_at,
                                    error_code="provider_unavailable",
                                    warning=f"Serper News request failed (HTTP {status})" if status else "Serper News request failed")
    except ValueError:
        return ProviderSearchResult(query=query, provider="serper_news", retrieved_at=retrieved_at,
                                    error_code="provider_invalid_response", warning="Serper News returned invalid JSON")
    finally:
        session.close()
