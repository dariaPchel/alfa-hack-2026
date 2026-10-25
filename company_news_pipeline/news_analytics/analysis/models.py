"""Validated analysis output with per-event impact and executable action plans."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Citation(StrictModel):
    source_id: str
    source_type: Literal["news", "web", "alfa_research", "risk_methodology", "rusprofile_analogue", "internal_profile"]
    title: str
    url: str | None = None
    published_at: str | None = None
    retrieved_at: str | None = None
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    content_hash: str | None = None
    analogue_only: bool = False


class KPIChange(StrictModel):
    metric: str
    direction: Literal["increase", "decrease", "mixed", "unknown"]
    unit: Literal["percent"] = "percent"
    change_pct_min: float
    change_pct_max: float
    baseline_basis: str
    period: str
    analogue_count: int = Field(ge=0)
    analogue_references: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ordered_range(self):
        if self.change_pct_min > self.change_pct_max:
            raise ValueError("change_pct_min must be <= change_pct_max")
        return self


class Evidence(StrictModel):
    statement: str
    source_id: str
    evidence_kind: Literal["direct_fact", "analogue_observation", "methodology", "inference"]
    confidence: float = Field(ge=0.0, le=1.0)
    limitations: list[str] = Field(default_factory=list)


class BankView(StrictModel):
    summary: str
    applicable_findings: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)
    applicability_limits: list[str] = Field(default_factory=list)


class MethodologyUse(StrictModel):
    method: str
    steps_applied: list[str] = Field(default_factory=list)
    jurisdiction_scope: str | None = None
    citation_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ActionStep(StrictModel):
    sequence: int = Field(ge=1)
    action: str = Field(min_length=8)
    owner: str = Field(min_length=2)
    due_in_days: int = Field(ge=0)
    dependencies: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(min_length=1)


class SupplierCandidate(StrictModel):
    supplier_name: str
    category: str
    region_fit: str
    source_ids: list[str] = Field(min_length=1)
    verification_status: Literal["verified", "conditional", "blocked"]
    fit_evidence: list[str] = Field(default_factory=list)


class SolutionPlan(StrictModel):
    solution_id: str
    title: str
    verification_status: Literal["verified", "conditional", "blocked"]
    objective: str = Field(min_length=10)
    target_item_or_category: str = Field(min_length=3)
    steps: list[ActionStep] = Field(min_length=1)
    responsible_owner: str
    timing: str
    dependencies: list[str] = Field(default_factory=list)
    resources_and_cost: str
    success_criteria: list[str] = Field(min_length=1)
    fallback_plan: str = Field(min_length=8)
    expected_kpi_changes: list[KPIChange] = Field(min_length=1)
    suppliers: list[SupplierCandidate] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    unresolved_confirmation: list[str] = Field(default_factory=list)
    residual_blockers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def steps_are_sequenced(self):
        sequence = [step.sequence for step in self.steps]
        if sequence != sorted(sequence) or len(sequence) != len(set(sequence)):
            raise ValueError("Action steps must have unique ascending sequence numbers")
        if self.verification_status == "verified" and self.unresolved_confirmation:
            raise ValueError("A verified plan cannot have unresolved confirmation items")
        return self


class CollaborationTask(StrictModel):
    task_id: str
    assigned_role: str
    question: str
    missing_field: str
    required_evidence: list[str] = Field(default_factory=list)
    status: Literal["assigned", "completed", "blocked"]


class CandidateEvidence(StrictModel):
    task_id: str
    source_id: str
    finding: str
    evidence_kind: Literal["direct_fact", "analogue_observation", "methodology", "inference"]
    limitations: list[str] = Field(default_factory=list)


class CriticFinding(StrictModel):
    field_path: str
    severity: Literal["info", "warning", "blocking"]
    finding: str
    required_revision: str | None = None
    source_ids: list[str] = Field(default_factory=list)


class NewsImpact(StrictModel):
    event_id: str
    title: str
    event_type: str
    qualitative_impact: Literal["risk", "opportunity", "mixed"]
    severity: Literal["low", "medium", "high"]
    likelihood: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    horizon: str = Field(min_length=2)
    why_relevant: str
    ai_analysis: str
    event_kpi_changes: list[KPIChange] = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)
    bank_view: BankView
    risk_method_used: list[MethodologyUse] = Field(default_factory=list)
    solutions: list[SolutionPlan] = Field(min_length=1)
    solution_gap_report: list[str] = Field(default_factory=list)
    collaboration_tasks: list[CollaborationTask] = Field(default_factory=list)
    candidate_evidence: list[CandidateEvidence] = Field(default_factory=list)
    critic_review: list[CriticFinding] = Field(default_factory=list)
    collaboration_trace: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class CompanyNewsAnalysis(StrictModel):
    synthetic_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    dataset_batch_id: int | None = None
    model_alias: str = "~z-ai/glm-flash-latest"
    status: Literal["complete", "partial", "blocked"]
    events: list[NewsImpact] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    trace: dict[str, Any] = Field(default_factory=dict)
