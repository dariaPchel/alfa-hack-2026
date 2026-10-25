"""Controller-directed multi-agent analysis and bounded solution refinement."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from ..company_profiles import get_company_profile
from ..db import Database
from ..payment_network import get_counterparty_industries
from ..peer_matching import find_peers
from ..search.models import NewsEvent
from ..search.refresh import get_company_news
from ..tools.policy import sanitize_outbound_query
from .agents import AgentRuntime, AnalysisBlocked
from .models import BankView, Citation, CompanyNewsAnalysis, CriticFinding, MethodologyUse, NewsImpact, SolutionPlan
from .repository import save_analysis


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Agent response must be a JSON object")
    return value


def _call(runtime: AgentRuntime, role: str, payload: dict[str, Any], warnings: list[str], trace: list[str], *, tools: bool = True) -> dict[str, Any]:
    try:
        response = runtime.run_role(role, payload, use_tools=tools)
        result = _parse_json(response["raw_json"])
        trace.append(f"{role}: completed")
        return result
    except AnalysisBlocked as exc:
        warnings.append(f"{role}: {exc}")
    except (ValueError, json.JSONDecodeError) as exc:
        warnings.append(f"{role}: response was not valid JSON ({exc})")
    except Exception:
        warnings.append(f"{role}: call failed")
    trace.append(f"{role}: unavailable")
    return {}


def _citations(event: NewsEvent) -> list[dict[str, Any]]:
    return [Citation(source_id=event.event_id, source_type="news", title=event.title,
                     url=event.url, published_at=event.published_at.isoformat() if event.published_at else None,
                     retrieved_at=event.retrieved_at.isoformat()).model_dump(mode="json")]


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _target_role(field_path: str) -> str:
    folded = field_path.casefold()
    if "bank" in folded or "alfa" in folded:
        return "Bank Research Analyst"
    if "method" in folded or "risk" in folded:
        return "Risk Methodology Analyst"
    if "source" in folded or "evidence" in folded or "date" in folded:
        return "News & Legal Researcher"
    return "Company Context / Peer Analyst"


def _event_analysis(event: NewsEvent, profile: dict[str, Any], peer_context: dict[str, Any],
                    runtime: AgentRuntime, warnings: list[str], trace: list[str]) -> NewsImpact | None:
    event_source = _citations(event)[0]
    base = {"event": event.model_dump(mode="json"), "company_profile": profile,
            "peer_context": peer_context, "required_output_schema": NewsImpact.model_json_schema()}
    research = _call(runtime, "News & Legal Researcher", {
        **base, "instruction": "Check event date and primary source; return verified facts and citations only."
    }, warnings, trace)
    base["news_legal_research"] = research
    classified = _call(runtime, "Evidence Classifier", {
        **base, "evidence_candidates": research,
        "instruction": "Classify each candidate as direct fact, analogue observation, methodology, or inference; preserve source IDs and date status."
    }, warnings, trace)
    base["classified_evidence"] = classified
    impact = _call(runtime, "Impact Analyst", base, warnings, trace)
    bank = _call(runtime, "Bank Research Analyst", base, warnings, trace)
    methodology = _call(runtime, "Risk Methodology Analyst", base, warnings, trace)
    first_action = _call(runtime, "Action Analyst", {**base, "impact_assessment": impact,
                          "bank_view": bank, "risk_method_used": methodology}, warnings, trace)

    action = first_action
    critic: dict[str, Any] = {}
    max_cycles = max(0, min(3, int(os.getenv("NEWS_ANALYTICS_COLLAB_CYCLES", "3"))))
    collaboration = []
    for cycle in range(max_cycles + 1):
        critic = _call(runtime, "Critic / Source Checker", {
            **base, "impact_assessment": impact, "bank_view": bank, "risk_method_used": methodology,
            "proposed_solutions": action.get("solutions") or action.get("action_plans"),
            "review_request": "Return field-specific blocking/warning findings; verify every evidence and source ID.",
        }, warnings, trace)
        findings = critic.get("findings", critic.get("critic_review", []))
        blockers = [finding for finding in findings if isinstance(finding, dict) and finding.get("severity") == "blocking"]
        if not blockers or cycle == max_cycles:
            break
        candidate_evidence = []
        for finding in blockers[:4]:
            role = _target_role(str(finding.get("field_path", "")))
            task = _call(runtime, role, {**base, "targeted_gap": finding,
                          "instruction": "Return concise source-backed findings for this gap as JSON."}, warnings, trace)
            candidate_evidence.append({"assigned_role": role, "finding": task})
        collaboration.append(f"cycle {cycle + 1}: assigned {len(candidate_evidence)} targeted evidence tasks")
        action = _call(runtime, "Action Analyst", {
            **base, "impact_assessment": impact, "bank_view": bank, "risk_method_used": methodology,
            "prior_solutions": action.get("solutions") or action.get("action_plans"),
            "critic_findings": blockers, "candidate_evidence": candidate_evidence,
            "instruction": "Revise the complete plan using assigned evidence; keep residual blockers explicit.",
        }, warnings, trace)

    impact = impact.get("impact", impact)
    solutions = action.get("solutions", action.get("action_plans", []))
    bank_data = bank.get("bank_view", bank)
    methodology_data = methodology.get("risk_method_used", methodology.get("methods", []))
    critic_data = critic.get("findings", critic.get("critic_review", []))
    citations = [event_source]
    for candidate in (impact, bank, methodology, action):
        for citation in candidate.get("citations", []) if isinstance(candidate, dict) else []:
            if isinstance(citation, dict):
                citations.append(citation)
    payload = {
        "event_id": event.event_id,
        "title": event.title,
        "event_type": impact.get("event_type", "industry_news"),
        "qualitative_impact": impact.get("qualitative_impact", "mixed"),
        "severity": impact.get("severity", "medium"),
        "likelihood": impact.get("likelihood", 0.5),
        "confidence": impact.get("confidence", 0.25),
        "horizon": impact.get("horizon", "3-12 months"),
        "why_relevant": impact.get("why_relevant", "Impact assessment was incomplete; treat this event as a monitoring signal."),
        "ai_analysis": impact.get("ai_analysis", impact.get("rationale", "")),
        "event_kpi_changes": impact.get("event_kpi_changes", impact.get("kpi_changes", [])),
        "evidence": [*impact.get("evidence", []), {
            "statement": event.snippet or event.title,
            "source_id": event.event_id,
            "evidence_kind": "direct_fact",
            "confidence": 0.8 if event.date_status == "parsed" else 0.5,
            "limitations": ["Provider result must be checked against the linked source page."],
        }],
        "bank_view": bank_data if isinstance(bank_data, dict) and "summary" in bank_data else {"summary": "No Alpha research evidence was returned."},
        "risk_method_used": methodology_data,
        "solutions": solutions,
        "solution_gap_report": action.get("solution_gap_report", action.get("gaps", [])),
        "collaboration_tasks": action.get("collaboration_tasks", []),
        "candidate_evidence": action.get("candidate_evidence", []),
        "critic_review": critic_data,
        "collaboration_trace": collaboration,
        "citations": citations,
    }
    try:
        return NewsImpact.model_validate(payload)
    except Exception as exc:
        warnings.append(f"Event {event.event_id} failed the final analysis schema: {exc}")
        return None


def analyze_company_news(synthetic_id: str, event_ids: list[str] | None = None,
                         db: Database | None = None,
                         peer_analogue_data: dict[str, Any] | None = None) -> CompanyNewsAnalysis:
    """Analyze each selected news event with bounded roles and per-solution review."""

    db = db or Database()
    db.initialize()
    profile_model = get_company_profile(synthetic_id, db)
    if profile_model is None:
        raise KeyError(f"Unknown synthetic company ID: {synthetic_id}")
    peers = find_peers(synthetic_id, db, limit=8)
    exposures = get_counterparty_industries(synthetic_id, db, limit=5)
    windows = get_company_news(synthetic_id, db, refresh_24h=True)
    events_by_id: dict[str, NewsEvent] = {}
    for window in ("24h", "7d", "90d"):
        for event in windows[window].events:
            events_by_id.setdefault(event.event_id, event)
    if event_ids is not None:
        requested = set(event_ids)
        events_by_id = {event_id: event for event_id, event in events_by_id.items() if event_id in requested}
    events = sorted(events_by_id.values(), key=lambda item: item.published_at or item.retrieved_at, reverse=True)[:20]
    profile = profile_model.model_dump(mode="json")
    peer_context = {
        "peers": [peer.model_dump(mode="json") for peer in peers],
        "counterparty_industries": [exposure.model_dump(mode="json") for exposure in exposures],
        "mock_data": profile_model.source_metadata.get("mock_data", False),
    }
    if peer_analogue_data is not None:
        peer_context["rusprofile_analogues"] = peer_analogue_data
    warnings = [warning for window in windows.values() for warning in window.warnings]
    trace: list[str] = []
    if not events:
        analysis = CompanyNewsAnalysis(
            synthetic_id=synthetic_id,
            dataset_batch_id=profile_model.source_metadata.get("dataset_batch_id"),
            status="partial", events=[], source_ids=[],
            warnings=list(dict.fromkeys(warnings + ["No dated news events are available for this company and selection."])),
            trace={"roles": [], "peer_count": len(peers), "event_count": 0},
        )
        save_analysis(db, analysis, [])
        return analysis
    runtime = AgentRuntime(db)
    context = _call(runtime, "Company Context / Peer Analyst", {"profile": profile, "peer_context": peer_context}, warnings, trace)
    if peer_analogue_data is not None:
        context["rusprofile_analogues"] = peer_analogue_data
    if events:
        planned = _call(runtime, "Search Planner", {"profile": profile, "event_count": len(events),
                        "categories": ["industry_news", "courts_crackdown", "regulator_action", "corporate_material_facts"]},
                        warnings, trace, tools=False)
        context["search_plan"] = planned
    analyzed = []
    for event in events:
        result = _event_analysis(event, profile, context, runtime, warnings, trace)
        if result is not None:
            analyzed.append(result)
    status = "complete" if events and len(analyzed) == len(events) and not warnings else "partial" if analyzed else "blocked"
    source_ids = sorted({citation.source_id for item in analyzed for citation in item.citations})
    analysis = CompanyNewsAnalysis(
        synthetic_id=synthetic_id,
        dataset_batch_id=profile_model.source_metadata.get("dataset_batch_id"),
        status=status,
        events=analyzed,
        source_ids=source_ids,
        warnings=list(dict.fromkeys(warnings)),
        trace={"roles": trace, "peer_count": len(peers), "event_count": len(events),
               "collaboration_cycles_per_solution_max": 3,
               "routerai_model": "~z-ai/glm-flash-latest"},
    )
    save_analysis(db, analysis, [event.event_id for event in events])
    return analysis
