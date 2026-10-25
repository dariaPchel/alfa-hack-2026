"""Atomic daily RouterAI budget reservation and usage accounting."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict

from .db import Database


DAILY_CAP_RUB = 500.0
MODEL_ALIAS = "~z-ai/glm-flash-latest"
EMBEDDING_MODEL_ALIAS = "intfloat/multilingual-e5-large"


class BudgetDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    request_id: str | None = None
    role: str
    model_alias: str
    estimated_tokens: int
    reserved_cost_rub: float
    remaining_budget_rub: float
    reason: str | None = None


class BudgetGate:
    def __init__(self, db: Database, daily_cap_rub: float = DAILY_CAP_RUB) -> None:
        self.db = db
        self.daily_cap_rub = daily_cap_rub
        self.rate_per_1k = float(os.getenv("ROUTERAI_ESTIMATED_RUB_PER_1K_TOKENS", "5"))
        self.embedding_rate_per_1k = float(os.getenv("ROUTERAI_EMBEDDING_RUB_PER_1M_TOKENS", "1.10")) / 1000

    def reserve_call(self, role: str, model: str, estimated_tokens: int) -> BudgetDecision:
        if model == EMBEDDING_MODEL_ALIAS:
            pass
        elif model != MODEL_ALIAS:
            return BudgetDecision(allowed=False, role=role, model_alias=model, estimated_tokens=estimated_tokens,
                                  reserved_cost_rub=0, remaining_budget_rub=self.daily_cap_rub,
                                  reason="Only the configured RouterAI model is allowed")
        if not os.getenv("ROUTERAI_API_KEY"):
            return BudgetDecision(allowed=False, role=role, model_alias=model, estimated_tokens=estimated_tokens,
                                  reserved_cost_rub=0, remaining_budget_rub=self.daily_cap_rub,
                                  reason="ROUTERAI_API_KEY is not configured")
        estimated_tokens = max(1, min(int(estimated_tokens), 100_000))
        rate = self.embedding_rate_per_1k if model == EMBEDDING_MODEL_ALIAS else self.rate_per_1k
        reserved = max(0.00001, estimated_tokens / 1000 * rate)
        now = datetime.now(timezone.utc)
        day = now.date().isoformat()
        request_id = uuid.uuid4().hex
        self.db.initialize()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            spent = connection.execute(
                """SELECT COALESCE(SUM(CASE WHEN status='completed' THEN COALESCE(actual_cost_rub, reserved_cost_rub)
                           WHEN status IN ('reserved','failed') THEN reserved_cost_rub ELSE 0 END), 0) AS total
                   FROM llm_budget_reservations WHERE day_key=?""", (day,),
            ).fetchone()["total"]
            remaining = max(0.0, self.daily_cap_rub - float(spent))
            if reserved > remaining:
                return BudgetDecision(allowed=False, role=role, model_alias=model, estimated_tokens=estimated_tokens,
                                      reserved_cost_rub=0, remaining_budget_rub=remaining,
                                      reason="Daily RouterAI budget is exhausted")
            connection.execute(
                """INSERT INTO llm_budget_reservations (request_id, day_key, role, model_alias,
                           estimated_tokens, reserved_cost_rub, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'reserved', ?)""",
                (request_id, day, role, model, estimated_tokens, reserved, now.isoformat()),
            )
        return BudgetDecision(allowed=True, request_id=request_id, role=role, model_alias=model,
                              estimated_tokens=estimated_tokens, reserved_cost_rub=reserved,
                              remaining_budget_rub=max(0.0, remaining-reserved))

    def record_usage(self, request_id: str, *, actual_tokens: int | None = None,
                     actual_cost_rub: float | None = None, failed: bool = False) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.db.connect() as connection:
            connection.execute(
                """UPDATE llm_budget_reservations SET actual_tokens=?, actual_cost_rub=?,
                          status=?, completed_at=? WHERE request_id=? AND status='reserved'""",
                (actual_tokens, actual_cost_rub, "failed" if failed else "completed", now, request_id),
            )
