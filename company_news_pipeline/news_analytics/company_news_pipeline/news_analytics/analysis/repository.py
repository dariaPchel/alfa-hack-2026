"""Persist final JSON analysis and concise provenance, never chain-of-thought."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from ..db import Database
from .models import CompanyNewsAnalysis


def save_analysis(db: Database, analysis: CompanyNewsAnalysis, event_ids: list[str]) -> str:
    analysis_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    payload = analysis.model_dump(mode="json")
    with db.connect() as connection:
        connection.execute(
            """INSERT INTO company_news_analyses (analysis_id, synthetic_id, dataset_batch_id,
                       event_ids_json, model_alias, status, source_ids_json, analysis_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (analysis_id, analysis.synthetic_id, analysis.dataset_batch_id,
             json.dumps(event_ids, ensure_ascii=False), analysis.model_alias, analysis.status,
             json.dumps(analysis.source_ids, ensure_ascii=False), json.dumps(payload, ensure_ascii=False), now, now),
        )
    return analysis_id


def get_latest_analysis(db: Database, synthetic_id: str) -> CompanyNewsAnalysis | None:
    with db.connect() as connection:
        row = connection.execute(
            "SELECT analysis_json FROM company_news_analyses WHERE synthetic_id=? ORDER BY created_at DESC LIMIT 1",
            (synthetic_id,),
        ).fetchone()
    return CompanyNewsAnalysis.model_validate_json(row["analysis_json"]) if row else None
