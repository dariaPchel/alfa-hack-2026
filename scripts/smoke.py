"""End-to-end check against a running Compose stack with live credentials and bank corpus."""

from __future__ import annotations

import argparse
import json
import time
from urllib.request import Request, urlopen


def request(base: str, path: str, payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(base + path, data=body, headers={"Content-Type": "application/json"},
                  method="POST" if body is not None else "GET")
    with urlopen(req, timeout=15) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:5173")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    health = request(base, "/healthz")
    if health.get("status") != "ok":
        raise RuntimeError(f"API unhealthy: {health}")
    companies = request(base, "/api/companies")["companies"]
    if not companies:
        raise RuntimeError("No companies: check importer logs and CSV paths")
    company = None
    event = None
    for candidate in companies:
        if candidate.get("datasetKind") == "demo":
            continue
        windows = request(base, f"/api/companies/{candidate['id']}/news")["windows"]
        events = next((windows[name]["events"] for name in ("24h", "7d", "90d")
                       if windows[name]["events"]), [])
        if events:
            company, event = candidate, events[0]
            break
    if company is None:
        raise RuntimeError("No dated news: check SERPER_API_KEY and news-worker logs")
    if not event.get("url"):
        raise RuntimeError("News event has no source URL")
    accepted = request(base, f"/api/companies/{company['id']}/analyze",
                       {"event_ids": [event["id"]],
                        "question": "Как это событие влияет на деятельность компании?"})
    analysis_id = accepted["analysis_id"]
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        analysis = request(base, f"/api/analyses/{analysis_id}")["analysis"]
        if analysis["status"] == "failed":
            raise RuntimeError(f"Analysis failed: {analysis.get('error')}")
        if analysis["status"] == "complete":
            if analysis.get("provenance") == "go-worker-demo":
                raise RuntimeError("Live smoke check received a demo result")
            if not analysis.get("ai_analysis") or not analysis.get("bank_view") or len(analysis.get("citations", [])) < 2:
                raise RuntimeError("Complete analysis lacks bank/news evidence or text")
            if not analysis.get("trace") or not analysis.get("question"):
                raise RuntimeError("Complete analysis lacks trace or user question")
            request(base, f"/api/analyses/{analysis_id}/feedback", {"rating": "useful"})
            print(f"PASS company={company['id']} event={event['id']} analysis={analysis_id}")
            return
        time.sleep(2)
    raise RuntimeError(f"Analysis {analysis_id} did not finish within five minutes")


if __name__ == "__main__":
    main()
