"""SQLite persistence and URL/content deduplication for news events."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from ..db import Database
from .models import NewsEvent, SearchWindow


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(event: NewsEvent) -> str:
    normalized = " ".join(f"{event.title} {event.snippet}".casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def start_query_run(db: Database, synthetic_id: str, window: str, query: str, category: str) -> tuple[int, str]:
    started = _now()
    with db.connect() as connection:
        cursor = connection.execute(
            """INSERT INTO news_query_runs (synthetic_id, window_name, query, category, provider,
                      status, started_at, finished_at) VALUES (?, ?, ?, ?, 'serper_news', 'failed', ?, ?)""",
            (synthetic_id, window, query, category, started, started),
        )
        return int(cursor.lastrowid), started


def finish_query_run(db: Database, run_id: int, *, count: int, status: str, error_code: str | None,
                     warning: str | None, finished_at: str | None = None) -> None:
    with db.connect() as connection:
        connection.execute(
            """UPDATE news_query_runs SET result_count = ?, status = ?, error_code = ?, warning = ?,
                      finished_at = ? WHERE id = ?""",
            (count, status, error_code, warning, finished_at or _now(), run_id),
        )


def persist_rejection(db: Database, synthetic_id: str, run_id: int, url: str | None,
                      title: str | None, reason: str, payload: dict) -> None:
    with db.connect() as connection:
        connection.execute(
            """INSERT INTO rejected_news_candidates (synthetic_id, query_run_id, candidate_url,
                      candidate_title, rejection_reason, provider_payload_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (synthetic_id, run_id, url, title, reason, json.dumps(payload, ensure_ascii=False), _now()),
        )


def persist_event(db: Database, synthetic_id: str, event: NewsEvent, *, run_id: int,
                  window: str, reasons: list[str], rank: int) -> None:
    now = _now()
    fingerprint = _fingerprint(event)
    with db.connect() as connection:
        existing = connection.execute(
            "SELECT event_id FROM news_events WHERE canonical_url = ?", (event.url,)
        ).fetchone()
        if existing is None:
            existing = connection.execute(
                "SELECT event_id FROM news_events WHERE content_fingerprint = ? ORDER BY first_seen_at LIMIT 1",
                (fingerprint,),
            ).fetchone()
        if existing is None:
            connection.execute(
            """INSERT INTO news_events (event_id, canonical_url, content_fingerprint, title, snippet,
                      publisher, provider_published_at, published_at, date_status, image_url, provider,
                      first_seen_at, last_seen_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(canonical_url) DO UPDATE SET
                  content_fingerprint=excluded.content_fingerprint,
                  title=CASE WHEN excluded.title <> '' THEN excluded.title ELSE news_events.title END,
                  snippet=CASE WHEN excluded.snippet <> '' THEN excluded.snippet ELSE news_events.snippet END,
                  publisher=COALESCE(excluded.publisher, news_events.publisher),
                  provider_published_at=COALESCE(excluded.provider_published_at, news_events.provider_published_at),
                  published_at=COALESCE(excluded.published_at, news_events.published_at),
                  date_status=CASE WHEN excluded.date_status='parsed' THEN 'parsed' ELSE news_events.date_status END,
                  image_url=COALESCE(excluded.image_url, news_events.image_url),
                  last_seen_at=excluded.last_seen_at""",
            (event.event_id, event.url, fingerprint, event.title, event.snippet, event.publisher,
             event.provider_published_at, event.published_at.isoformat() if event.published_at else None,
             event.date_status, event.image_url, event.provider, now, now),
            )
            event_id = event.event_id
        else:
            event_id = existing["event_id"]
            connection.execute("UPDATE news_events SET last_seen_at=? WHERE event_id=?", (now, event_id))
        connection.execute(
            """INSERT INTO company_news_links (synthetic_id, event_id, query_run_id, window_name,
                      matched_search_query, profile_reasons_json, selection_rank, first_seen_at, last_seen_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(synthetic_id, event_id, query_run_id) DO UPDATE SET
                   selection_rank=excluded.selection_rank, last_seen_at=excluded.last_seen_at""",
            (synthetic_id, event_id, run_id, window, event.query,
             json.dumps(reasons, ensure_ascii=False), rank, now, now),
        )


def save_window_status(db: Database, synthetic_id: str, window: str, status: str,
                       started_at: str, error: str | None = None) -> None:
    finished = _now()
    with db.connect() as connection:
        connection.execute(
            """INSERT INTO company_news_window_status (synthetic_id, window_name, last_started_at,
                      last_success_at, last_error, status) VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(synthetic_id, window_name) DO UPDATE SET
                   last_started_at=excluded.last_started_at,
                   last_success_at=CASE WHEN excluded.status IN ('success','partial') THEN excluded.last_success_at ELSE company_news_window_status.last_success_at END,
                   last_error=excluded.last_error, status=excluded.status""",
            (synthetic_id, window, started_at, finished if status in {"success", "partial"} else None, error, status),
        )


def get_window(db: Database, synthetic_id: str, window: str, limit: int) -> SearchWindow:
    now = datetime.now(timezone.utc)
    duration = {"90d": 90, "7d": 7, "24h": 1}.get(window)
    if duration is None:
        raise ValueError("Unknown news window")
    cutoff = (now - (timedelta(hours=24) if window == "24h" else timedelta(days=duration))).isoformat()
    with db.connect() as connection:
        status = connection.execute(
            "SELECT last_success_at, last_error, status FROM company_news_window_status WHERE synthetic_id=? AND window_name=?",
            (synthetic_id, window),
        ).fetchone()
        rows = connection.execute(
            """SELECT e.*, l.matched_search_query, l.selection_rank, l.last_seen_at
               FROM news_events e JOIN company_news_links l ON l.event_id=e.event_id
               WHERE l.synthetic_id=? AND l.window_name=?
                 AND e.published_at IS NOT NULL AND e.published_at >= ? AND e.published_at <= ?
               GROUP BY e.event_id
               ORDER BY COALESCE(e.published_at, MAX(l.last_seen_at)) DESC,
                        MIN(l.selection_rank), e.event_id
               LIMIT ?""",
            (synthetic_id, window, cutoff, now.isoformat(), limit),
        ).fetchall()
    from .serper_news import _canonical_url
    events = []
    for row in rows:
        events.append(NewsEvent(
            event_id=row["event_id"], title=row["title"], url=_canonical_url(row["canonical_url"]),
            snippet=row["snippet"], publisher=row["publisher"],
            provider_published_at=row["provider_published_at"],
            published_at=datetime.fromisoformat(row["published_at"]) if row["published_at"] else None,
            date_status=row["date_status"], image_url=row["image_url"],
            provider_rank=row["selection_rank"], query=row["matched_search_query"],
            retrieved_at=datetime.fromisoformat(row["last_seen_at"]), provider=row["provider"],
        ))
    updated = datetime.fromisoformat(status["last_success_at"]) if status and status["last_success_at"] else None
    warnings = [status["last_error"]] if status and status["last_error"] else []
    return SearchWindow(synthetic_id=synthetic_id, window=window, requested_limit=limit,
                        actual_count=len(events), updated_at=updated, events=events, warnings=warnings)
