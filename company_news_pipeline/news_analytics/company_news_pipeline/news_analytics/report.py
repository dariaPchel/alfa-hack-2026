"""Assemble the public v1 company pipeline report from persisted evidence."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .analysis.models import CompanyNewsAnalysis, NewsImpact, SolutionPlan
from .db import Database
from .models import CompanyProfile, PeerProfile
from .search.models import NewsEvent, SearchWindow


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _qualitative(value: float) -> str:
    if value < 0.4:
        return "low"
    if value < 0.7:
        return "medium"
    return "high"


def _horizon(value: str, generated_at: datetime) -> dict[str, str | None]:
    start = generated_at.date()
    match = re.search(r"(\d+)\s*(?:-|–|to)\s*(\d+)\s*(day|week|month|year)s?", value, re.I)
    if not match:
        match = re.search(r"(\d+)\s*(day|week|month|year)s?", value, re.I)
        first, last, unit = (int(match.group(1)), int(match.group(1)), match.group(2).casefold()) if match else (None, None, None)
    else:
        first, last, unit = int(match.group(1)), int(match.group(2)), match.group(3).casefold()
    factors = {"day": 1, "week": 7, "month": 30, "year": 365}
    end = (start + timedelta(days=last * factors[unit])).isoformat() if last is not None and unit else None
    return {"label": value, "start": start.isoformat(), "end": end}


def _citation_source(citation: dict[str, Any]) -> dict[str, Any]:
    source_type = citation.get("source_type", "web")
    source = {
        "source_id": citation["source_id"],
        "source_type": source_type,
        "title": citation.get("title") or citation["source_id"],
        "url": citation.get("url"),
        "published_at": citation.get("published_at"),
        "retrieved_at": citation.get("retrieved_at"),
    }
    page = citation.get("page_start") or citation.get("page_end")
    if page is not None:
        source["page"] = page
    if source_type in {"alfa_research", "risk_methodology"}:
        source["knowledge_store"] = source_type
    return source


def _kpi_change(change: Any, source_ids: list[str]) -> dict[str, Any]:
    return {
        "metric": change.metric,
        "direction": change.direction,
        "change_pct": {"min": change.change_pct_min, "max": change.change_pct_max},
        "period": change.period,
        "baseline_basis": change.baseline_basis,
        "analogue_count": change.analogue_count,
        "assumptions": change.assumptions,
        "source_ids": _unique([*source_ids, *change.analogue_references]),
    }


def _solution(solution: SolutionPlan, generated_at: datetime, impact_confidence: float) -> dict[str, Any]:
    source_ids = _unique([citation.source_id for citation in solution.citations])
    steps = [step.model_dump(mode="json") for step in solution.steps]
    action = "\n".join(
        f"{step.sequence}. {step.owner}: {step.action} (срок: {step.due_in_days} дн.; "
        f"критерии: {'; '.join(step.completion_criteria)})"
        for step in solution.steps
    )
    conditions = _unique([*solution.dependencies, *solution.unresolved_confirmation,
                           *solution.residual_blockers])
    return {
        "solution_id": solution.solution_id,
        "action": action,
        "comparison": "Сценарий без реализации предложенного плана",
        "rationale": solution.objective,
        "expected_change_pct": [
            _kpi_change(change, source_ids) for change in solution.expected_kpi_changes
        ],
        "horizon": _horizon(solution.timing, generated_at),
        "confidence": _qualitative(impact_confidence),
        "assumptions": solution.assumptions,
        "costs_and_side_effects": [solution.resources_and_cost],
        "conditions": conditions,
        "source_ids": source_ids,
        "title": solution.title,
        "verification_status": solution.verification_status,
        "objective": solution.objective,
        "target_item_or_category": solution.target_item_or_category,
        "steps": steps,
        "responsible_owner": solution.responsible_owner,
        "timing": solution.timing,
        "dependencies": solution.dependencies,
        "resources_and_cost": solution.resources_and_cost,
        "success_criteria": solution.success_criteria,
        "fallback_plan": solution.fallback_plan,
        "suppliers": [supplier.model_dump(mode="json") for supplier in solution.suppliers],
        "citations": [citation.model_dump(mode="json") for citation in solution.citations],
    }


def _event_report(
    impact: NewsImpact,
    event: NewsEvent | None,
    peers: list[PeerProfile],
    generated_at: datetime,
) -> dict[str, Any]:
    source_ids = _unique([citation.source_id for citation in impact.citations])
    source_ids = _unique([*source_ids, *(evidence.source_id for evidence in impact.evidence)])
    matched_features = _unique([feature for peer in peers for feature in peer.matched_features])
    return {
        "event_id": impact.event_id,
        "title": impact.title,
        "summary": event.snippet if event and event.snippet else impact.ai_analysis,
        "event_type": impact.event_type,
        "event_date": event.published_at.date().isoformat() if event and event.published_at else None,
        "source_ids": source_ids,
        "relevance": {"explanation": impact.why_relevant, "matched_features": matched_features},
        "impact": {
            "impact_type": impact.qualitative_impact,
            "severity": impact.severity,
            "likelihood": _qualitative(impact.likelihood),
            "confidence": _qualitative(impact.confidence),
            "rationale": impact.ai_analysis,
            "horizon": _horizon(impact.horizon, generated_at),
            "business_metric_impacts": [
                _kpi_change(change, source_ids) for change in impact.event_kpi_changes
            ],
        },
        "solutions": [_solution(solution, generated_at, impact.confidence) for solution in impact.solutions],
        "warnings": _unique([*impact.solution_gap_report,
                              *(finding.finding for finding in impact.critic_review
                                if finding.severity in {"warning", "blocking"})]),
    }


def _industry_signals(db: Database, synthetic_id: str) -> list[dict[str, Any]]:
    category_names = {
        "courts_crackdown": ("court_activity", "публикации по судебной активности"),
        "regulator_action": ("regulatory_activity", "публикации о действиях регуляторов"),
        "corporate_material_facts": ("corporate_material_facts", "публикации о существенных фактах"),
    }
    grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
    now = datetime.now(timezone.utc)
    with db.connect() as connection:
        rows = connection.execute(
            """SELECT DISTINCT l.window_name, l.event_id, l.profile_reasons_json, e.published_at
               FROM company_news_links AS l
               JOIN news_events AS e ON e.event_id=l.event_id
               WHERE l.synthetic_id=? AND l.window_name IN ('90d','7d','24h')""",
            (synthetic_id,),
        ).fetchall()
    for row in rows:
        try:
            published_at = datetime.fromisoformat(row["published_at"])
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        max_age = {"24h": timedelta(hours=24), "7d": timedelta(days=7),
                   "90d": timedelta(days=90)}[row["window_name"]]
        if published_at < now - max_age or published_at > now:
            continue
        try:
            reasons = json.loads(row["profile_reasons_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            continue
        category = next((value for value in reasons if value in category_names), None)
        if category:
            grouped[(category, row["window_name"])].add(row["event_id"])
    signals = []
    for (category, period), event_ids in sorted(grouped.items()):
        signal_type, description = category_names[category]
        count = len(event_ids)
        signals.append({
            "signal_type": signal_type,
            "period": period,
            "description": (f"Обнаружено {count} публикаций через поисковые запросы по теме: {description}. "
                            "Количество результатов само по себе не подтверждает рост нарушений или crackdown."),
            "count": count,
            "confidence": "low",
            "source_ids": sorted(event_ids),
        })
    return signals


def build_pipeline_report(
    *,
    synthetic_id: str,
    profile: CompanyProfile,
    peers: list[PeerProfile],
    rusprofile: dict[str, Any],
    windows: dict[str, SearchWindow],
    analysis: CompanyNewsAnalysis,
    db: Database,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc)
    all_news: dict[str, NewsEvent] = {}
    for window in windows.values():
        for event in window.events:
            all_news.setdefault(event.event_id, event)

    sources: dict[str, dict[str, Any]] = {}
    for event in all_news.values():
        sources[event.event_id] = {
            "source_id": event.event_id,
            "source_type": "news",
            "title": event.title,
            "url": event.url,
            "published_at": event.published_at.isoformat() if event.published_at else None,
            "retrieved_at": event.retrieved_at.isoformat(),
        }
    for impact in analysis.events:
        for citation in impact.citations:
            sources[citation.source_id] = _citation_source(citation.model_dump(mode="json"))

    analogue_sources = []
    analogues = rusprofile.get("analogues") or []
    for analogue in analogues:
        if not analogue.get("url"):
            continue
        source_id = f"rusprofile:{analogue.get('rusprofile_id') or len(analogue_sources) + 1}"
        analogue_sources.append(source_id)
        sources[source_id] = {
            "source_id": source_id,
            "source_type": "rusprofile_analogue",
            "title": analogue.get("name") or "Rusprofile analogue",
            "url": analogue["url"],
            "retrieved_at": analogue.get("retrieved_at"),
            "analogue_only": True,
        }

    referenced_source_ids = set(analysis.source_ids)
    for impact in analysis.events:
        referenced_source_ids.update(item.source_id for item in impact.evidence)
        referenced_source_ids.update(impact.bank_view.citation_ids)
        for method in impact.risk_method_used:
            referenced_source_ids.update(method.citation_ids)
        for solution in impact.solutions:
            referenced_source_ids.update(citation.source_id for citation in solution.citations)
        for item in impact.candidate_evidence:
            referenced_source_ids.add(item.source_id)
        for finding in impact.critic_review:
            referenced_source_ids.update(finding.source_ids)
    missing_source_metadata = sorted(source_id for source_id in referenced_source_ids if source_id not in sources)
    for source_id in missing_source_metadata:
        sources[source_id] = {
            "source_id": source_id,
            "source_type": "unknown",
            "title": "Source metadata unavailable",
            "url": None,
        }

    feature_names = {
        "okved": "okved",
        "ownership_type": "legal_form",
        "region": "region",
        "scale": "revenue_band",
        "age_stage": "company_age_band",
        "product_trade_network": "payment_industry_exposure",
    }
    used_features = {
        feature_names[feature]
        for peer in peers for feature, score in peer.feature_scores.items()
        if feature in feature_names and score is not None
    }
    if profile.amount_workers_fns_gradation or profile.amount_workers_spark_gradation:
        used_features.add("employee_band")
    if profile.revenue_company:
        used_features.add("revenue_band")

    peer_warnings = []
    if isinstance(rusprofile.get("warning"), str) and rusprofile["warning"]:
        peer_warnings.append(rusprofile["warning"])
    if not peers:
        peer_warnings.append("В активном наборе не найдено синтетических компаний-аналогов.")
    warnings = [*analysis.warnings, *peer_warnings]
    if missing_source_metadata:
        warnings.append(f"Не удалось получить метаданные для источников: {', '.join(missing_source_metadata)}")
    for name in ("90d", "7d"):
        updated_at = windows[name].updated_at
        if updated_at is None:
            warnings.append(f"Для окна {name} ещё нет успешного обновления.")
        elif (generated_at - updated_at).total_seconds() > 36 * 3600:
            warnings.append(f"Данные окна {name} устарели; проверьте ежедневный worker.")
    event_reports = [_event_report(impact, all_news.get(impact.event_id), peers, generated_at)
                     for impact in analysis.events]
    signal_counts: dict[str, int] = defaultdict(int)
    for impact in analysis.events:
        signal_counts[impact.qualitative_impact] += 1
    if not analysis.events:
        overall_signal = "mixed"
    else:
        highest_count = max(signal_counts.values())
        leaders = [key for key, count in signal_counts.items() if count == highest_count]
        overall_signal = leaders[0] if len(leaders) == 1 else "mixed"
    summaries = _unique([impact.ai_analysis for impact in analysis.events])
    bank_summaries = _unique([impact.bank_view.summary for impact in analysis.events])
    bank_citations = _unique([citation_id for impact in analysis.events
                               for citation_id in impact.bank_view.citation_ids])
    methods = _unique([method.method for impact in analysis.events for method in impact.risk_method_used])
    method_refs = _unique([citation_id for impact in analysis.events
                           for method in impact.risk_method_used for citation_id in method.citation_ids])

    for window in windows.values():
        warnings.extend(window.warnings)
    roles = analysis.trace.get("roles", [])
    return {
        "schema_version": "1.0",
        "request_id": f"req_{uuid4().hex}",
        "synthetic_id": synthetic_id,
        "generated_at": generated_at.isoformat(),
        "model": {
            "provider": "routerai",
            "requested_alias": analysis.model_alias,
            "resolved_model": None,
        },
        "windows": {
            name: {"updated_at": window.updated_at.isoformat() if window.updated_at else None,
                   "returned_count": window.actual_count}
            for name, window in windows.items()
        },
        "peer_basis": {
            "synthetic_peer_count": len(peers),
            "rusprofile_analogue_count": sum(bool(item.get("rusprofile_id")) for item in analogues),
            "features_used": sorted(used_features),
            "warnings": _unique(peer_warnings),
        },
        "industry_signals": _industry_signals(db, synthetic_id),
        "sources": list(sources.values()),
        "bank_view": {
            "summary": " ".join(bank_summaries),
            "citations": bank_citations,
        },
        "risk_method_used": {
            "summary": " ".join(methods),
            "references": method_refs,
        },
        "ai_analysis": {
            "summary": " ".join(summaries) if summaries else "Анализ не сформирован: нет доступных датированных новостей.",
            "overall_signal": overall_signal,
        },
        "events": event_reports,
        "analysis_trace": {
            "roles_completed": [entry.rsplit(":", 1)[0] for entry in roles if entry.endswith(": completed")],
            "profile_version": str(analysis.dataset_batch_id) if analysis.dataset_batch_id is not None else None,
            "model_alias": analysis.model_alias,
            "chain_of_thought_included": False,
        },
        "warnings": _unique(warnings),
    }
