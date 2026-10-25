"""Bounded daily refresh worker; call once from a host/container scheduler."""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from ..db import Database
from .refresh import refresh_company_windows


def run_daily_refresh(company_ids: list[str] | None = None, db: Database | None = None) -> dict[str, Any]:
    db = db or Database()
    db.initialize()
    if company_ids is None:
        with db.connect() as connection:
            active = connection.execute("SELECT import_batch_id FROM active_dataset WHERE singleton_id=1").fetchone()
            if not active:
                return {"status": "failed", "companies": [], "warning": "No active company dataset"}
            company_ids = [row["synthetic_id"] for row in connection.execute(
                "SELECT synthetic_id FROM synthetic_companies WHERE import_batch_id=? ORDER BY synthetic_id",
                (active["import_batch_id"],),
            ).fetchall()]
    company_ids = list(dict.fromkeys(company_ids))
    workers = max(1, min(8, int(os.getenv("NEWS_ANALYTICS_REFRESH_WORKERS", "3"))))
    summaries = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="news-refresh") as executor:
        future_to_id = {executor.submit(refresh_company_windows, synthetic_id, db): synthetic_id
                        for synthetic_id in company_ids}
        for future in as_completed(future_to_id):
            synthetic_id = future_to_id[future]
            try:
                result = future.result()
                summaries.append({"synthetic_id": synthetic_id, "status": "success",
                                  "windows": {name: {"count": value.actual_count, "warnings": value.warnings}
                                              for name, value in result.items()}})
            except Exception as exc:
                summaries.append({"synthetic_id": synthetic_id, "status": "failed", "warning": str(exc)})
    return {"status": "success" if all(item["status"] == "success" for item in summaries) else "partial",
            "company_count": len(company_ids), "companies": sorted(summaries, key=lambda item: item["synthetic_id"])}


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh 90-day and 7-day news for each synthetic company")
    parser.add_argument("--company-id", action="append", dest="company_ids")
    args = parser.parse_args()
    print(json.dumps(run_daily_refresh(args.company_ids), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
