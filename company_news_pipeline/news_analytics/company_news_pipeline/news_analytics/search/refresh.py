"""Daily per-ID 90/7-day refresh and request-time 24-hour retrieval."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from ..company_profiles import get_company_profile
from ..db import Database
from ..payment_network import get_counterparty_industries
from .models import NewsEvent, ProviderSearchResult, SearchWindow
from .query_plan import SearchQuery, build_company_queries
from .repository import (
    finish_query_run,
    get_window,
    persist_event,
    persist_rejection,
    save_window_status,
    start_query_run,
)
from .serper_news import search_serper_news


NewsWindow = Literal["90d", "7d", "24h"]
WINDOW_LIMITS: dict[str, int] = {"90d": 20, "7d": 20, "24h": 10}
WINDOW_DURATION: dict[str, timedelta] = {
    "90d": timedelta(days=90), "7d": timedelta(days=7), "24h": timedelta(hours=24),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _within_window(event: NewsEvent, window: NewsWindow, now: datetime) -> tuple[bool, str | None]:
    if event.published_at is None:
        return False, "undated" if event.date_status == "undated" else "unparseable_date"
    if event.published_at < now - WINDOW_DURATION[window]:
        return False, "outside_window_before_cutoff"
    if event.published_at > now + timedelta(minutes=5):
        return False, "future_publication_date"
    return True, None


def _query_plan(synthetic_id: str, db: Database) -> tuple[list[SearchQuery], list[str]]:
    profile = get_company_profile(synthetic_id, db)
    if profile is None:
        raise KeyError(f"Unknown synthetic company ID: {synthetic_id}")
    exposures = get_counterparty_industries(synthetic_id, db, limit=3)
    queries = build_company_queries(synthetic_id, profile, exposures)
    max_queries = max(1, int(os.getenv("NEWS_ANALYTICS_MAX_QUERIES_PER_ID", "9")))
    warnings = []
    if len(queries) > max_queries:
        warnings.append(f"Search plan capped from {len(queries)} to {max_queries} queries per company/window")
    return queries[:max_queries], warnings


def _refresh_window(
    synthetic_id: str,
    db: Database,
    window: NewsWindow,
    *,
    search_fn=search_serper_news,
) -> SearchWindow:
    started_at = _now().isoformat()
    now = _now()
    queries, warnings = _query_plan(synthetic_id, db)
    matched: dict[str, list[tuple[int, NewsEvent, list[str], int]]] = {}
    successful = 0
    failed = 0

    for planned in queries:
        run_id, _ = start_query_run(db, synthetic_id, window, planned.query, planned.category)
        provider_result: ProviderSearchResult = search_fn(planned.query, WINDOW_LIMITS[window], window)
        if provider_result.error_code:
            failed += 1
            finish_query_run(db, run_id, count=0, status="failed", error_code=provider_result.error_code,
                             warning=provider_result.warning, finished_at=provider_result.retrieved_at.isoformat())
            warnings.append(provider_result.warning or provider_result.error_code)
            continue
        successful += 1
        if provider_result.warning:
            warnings.append(provider_result.warning)
        selected_count = 0
        for event in provider_result.results:
            allowed, rejection = _within_window(event, window, now)
            if not allowed:
                persist_rejection(db, synthetic_id, run_id, event.url, event.title,
                                  rejection or "outside_window", event.model_dump(mode="json"))
                continue
            reasons = [planned.category, planned.rationale]
            matched.setdefault(event.event_id, []).append((run_id, event, reasons, event.provider_rank or 10_000))
            selected_count += 1
        finish_query_run(db, run_id, count=selected_count,
                         status="success" if not provider_result.warning else "partial",
                         error_code=None, warning=provider_result.warning,
                         finished_at=provider_result.retrieved_at.isoformat())

    candidates = sorted(
        matched.items(),
        key=lambda item: (
            item[1][0][1].published_at or datetime.min.replace(tzinfo=timezone.utc),
            -item[1][0][3], item[0],
        ),
        reverse=True,
    )
    selected = candidates[:WINDOW_LIMITS[window]]
    for rank, (_, links) in enumerate(selected, start=1):
        for run_id, event, reasons, _ in links:
            persist_event(db, synthetic_id, event, run_id=run_id, window=window, reasons=reasons, rank=rank)

    status = "failed" if not successful else "partial" if failed or warnings else "success"
    error = "; ".join(dict.fromkeys(warnings)) or None
    save_window_status(db, synthetic_id, window, status, started_at, error)
    window_data = get_window(db, synthetic_id, window, WINDOW_LIMITS[window])
    window_data.warnings = list(dict.fromkeys([*window_data.warnings, *warnings]))
    if not window_data.events and successful:
        window_data.warnings.append(f"No dated articles fell within the strict {window} cutoff")
    return window_data


def refresh_company_windows(synthetic_id: str, db: Database) -> dict[str, SearchWindow]:
    """Refresh historical snapshots for exactly one synthetic company ID."""

    return {
        "90d": _refresh_window(synthetic_id, db, "90d"),
        "7d": _refresh_window(synthetic_id, db, "7d"),
    }


def get_company_news(synthetic_id: str, db: Database, refresh_24h: bool = True) -> dict[str, SearchWindow]:
    """Return stored 90/7-day windows and optionally query a fresh 24-hour set."""

    historical = {
        "90d": get_window(db, synthetic_id, "90d", 20),
        "7d": get_window(db, synthetic_id, "7d", 20),
    }
    if refresh_24h:
        historical["24h"] = _refresh_window(synthetic_id, db, "24h")
    else:
        historical["24h"] = get_window(db, synthetic_id, "24h", 10)
    return historical
