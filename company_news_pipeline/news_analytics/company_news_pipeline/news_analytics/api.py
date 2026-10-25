"""Flask API and dashboard for the anonymized-company news pipeline."""

from __future__ import annotations

import re
from typing import Any

from flask import Blueprint, jsonify, render_template, request

from .analysis.orchestrator import analyze_company_news
from .analysis.repository import get_latest_analysis
from .company_profiles import get_company_profile
from .db import Database
from .peer_matching import find_peers
from .report import build_pipeline_report
from .rusprofile_analogues import enrich_rusprofile_analogues
from .search.repository import get_window
from .search.refresh import get_company_news
from .search.service import company_news_response


news_analytics_api = Blueprint(
    "news_analytics",
    __name__,
    template_folder="../templates",
    static_folder="../static",
    static_url_path="/company-news-assets",
)
_SYNTHETIC_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _db() -> Database:
    database = Database()
    database.initialize()
    return database


def _error(code: str, message: str, status: int):
    return jsonify({"success": False, "error_code": code, "message": message}), status


def _valid_id(value: str) -> bool:
    return bool(_SYNTHETIC_ID.fullmatch(value))


@news_analytics_api.get("/api/companies")
def list_companies():
    database = _db()
    with database.connect() as connection:
        active = connection.execute("SELECT import_batch_id FROM active_dataset WHERE singleton_id=1").fetchone()
        if not active:
            return jsonify({"success": True, "companies": [], "warnings": ["No company dataset has been imported"]})
        rows = connection.execute(
            """SELECT synthetic_id, mainokved_code, mainokved_name, org_type, okfs_name,
                      region, city, revenue_company, amount_workers_fns_gradation
               FROM synthetic_companies WHERE import_batch_id=? ORDER BY synthetic_id""",
            (active["import_batch_id"],),
        ).fetchall()
    return jsonify({"success": True, "dataset_batch_id": active["import_batch_id"],
                    "companies": [dict(row) for row in rows], "count": len(rows)})


@news_analytics_api.get("/api/companies/<synthetic_id>/news")
def company_news(synthetic_id: str):
    if not _valid_id(synthetic_id):
        return _error("invalid_company_id", "Synthetic company ID has an invalid format", 400)
    database = _db()
    if get_company_profile(synthetic_id, database) is None:
        return _error("company_not_found", "Synthetic company was not found", 404)
    try:
        response = company_news_response(synthetic_id, database, refresh_24h=True)
    except Exception:
        return _error("news_unavailable", "Company news is temporarily unavailable", 503)
    return jsonify({"success": True, **response.model_dump(mode="json")})


@news_analytics_api.get("/api/companies/<synthetic_id>/news/<event_id>")
def company_news_event(synthetic_id: str, event_id: str):
    if not _valid_id(synthetic_id) or not re.fullmatch(r"[a-f0-9]{24}", event_id):
        return _error("invalid_identifier", "Company or event ID has an invalid format", 400)
    database = _db()
    with database.connect() as connection:
        row = connection.execute(
            """SELECT e.* FROM news_events e JOIN company_news_links l ON l.event_id=e.event_id
               WHERE l.synthetic_id=? AND e.event_id=? LIMIT 1""",
            (synthetic_id, event_id),
        ).fetchone()
    if row is None:
        return _error("event_not_found", "Event does not belong to this company or was not found", 404)
    analysis = get_latest_analysis(database, synthetic_id)
    analysis_event = next((item.model_dump(mode="json") for item in analysis.events if item.event_id == event_id), None) if analysis else None
    return jsonify({"success": True, "event": dict(row), "analysis": analysis_event,
                    "analysis_status": analysis.status if analysis else "not_analyzed"})


@news_analytics_api.post("/api/companies/<synthetic_id>/analyze")
def analyze_company(synthetic_id: str):
    if not _valid_id(synthetic_id):
        return _error("invalid_company_id", "Synthetic company ID has an invalid format", 400)
    payload: dict[str, Any] = request.get_json(silent=True) or {}
    event_ids = payload.get("event_ids")
    if event_ids is not None and (not isinstance(event_ids, list) or len(event_ids) > 20
                                  or any(not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{24}", value) for value in event_ids)):
        return _error("invalid_event_ids", "event_ids must be a list of at most 20 event IDs", 400)
    database = _db()
    if get_company_profile(synthetic_id, database) is None:
        return _error("company_not_found", "Synthetic company was not found", 404)
    if event_ids:
        with database.connect() as connection:
            owned = {row["event_id"] for row in connection.execute(
                "SELECT DISTINCT event_id FROM company_news_links WHERE synthetic_id=?", (synthetic_id,)
            ).fetchall()}
        if not set(event_ids).issubset(owned):
            return _error("event_not_found", "One or more events do not belong to this company", 404)
    try:
        result = analyze_company_news(synthetic_id, event_ids=event_ids, db=database)
    except KeyError:
        return _error("company_not_found", "Synthetic company was not found", 404)
    except Exception:
        return _error("analysis_unavailable", "Analysis could not be completed; inspect service status and budget", 503)
    return jsonify({"success": True, **result.model_dump(mode="json")})


@news_analytics_api.post("/api/companies/<synthetic_id>/pipeline")
def company_pipeline(synthetic_id: str):
    """Run fresh news collection, per-event analysis, and v1 report assembly."""

    if not _valid_id(synthetic_id):
        return _error("invalid_company_id", "Synthetic company ID has an invalid format", 400)
    payload = request.get_json(silent=True)
    if payload is not None and not isinstance(payload, dict):
        return _error("invalid_request", "Request body must be a JSON object", 400)
    payload = payload or {}
    event_ids = payload.get("event_ids")
    if event_ids is not None and (
        not isinstance(event_ids, list) or len(event_ids) > 20
        or any(not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{24}", value) for value in event_ids)
    ):
        return _error("invalid_event_ids", "event_ids must be a list of at most 20 event IDs", 400)

    database = _db()
    profile = get_company_profile(synthetic_id, database)
    if profile is None:
        return _error("company_not_found", "Synthetic company was not found", 404)
    if event_ids:
        with database.connect() as connection:
            owned = {row["event_id"] for row in connection.execute(
                "SELECT DISTINCT event_id FROM company_news_links WHERE synthetic_id=?", (synthetic_id,)
            ).fetchall()}
        if not set(event_ids).issubset(owned):
            return _error("event_not_found", "One or more events do not belong to this company", 404)

    try:
        try:
            rusprofile = enrich_rusprofile_analogues(profile)
        except Exception as exc:
            rusprofile = {"status": "unavailable", "analogues": [],
                          "warning": f"Rusprofile analogue lookup failed: {type(exc).__name__}"}
        analysis = analyze_company_news(
            synthetic_id, event_ids=event_ids, db=database, peer_analogue_data=rusprofile
        )
        windows = get_company_news(synthetic_id, database, refresh_24h=False)
        peers = find_peers(synthetic_id, database, limit=8)
        report = build_pipeline_report(
            synthetic_id=synthetic_id,
            profile=profile,
            peers=peers,
            rusprofile=rusprofile,
            windows=windows,
            analysis=analysis,
            db=database,
        )
    except KeyError:
        return _error("company_not_found", "Synthetic company was not found", 404)
    except Exception:
        return _error("pipeline_unavailable", "The company pipeline could not complete; inspect service logs", 503)
    return jsonify(report)


@news_analytics_api.get("/news")
def news_dashboard():
    return render_template("company_news.html")
