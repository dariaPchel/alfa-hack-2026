"""Bounded AG2 role execution with shared model, budget, network and tool gates."""

from __future__ import annotations

from typing import Any

from ..budget import BudgetGate, MODEL_ALIAS
from ..db import Database
from ..llm_config import build_autogen_llm_config
from ..tools.autogen_adapter import register_tools
from ..tools.catalog import build_default_registry
from ..tools.executor import ToolExecutor
from .prompts import ROLE_INSTRUCTIONS, SYSTEM_JSON_RULES


class AnalysisBlocked(RuntimeError):
    pass


class AgentRuntime:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.budget = BudgetGate(db)
        self.registry = build_default_registry(db)
        self.tools = ToolExecutor(self.registry, max_workers=6, db=db)

    def run_role(self, role: str, payload: dict[str, Any], *, use_tools: bool = True) -> dict[str, Any]:
        if role not in ROLE_INSTRUCTIONS:
            raise ValueError(f"Unknown analysis role: {role}")
        prompt = (
            "Analyze this role assignment. Return a single JSON object with your findings, evidence IDs, "
            "assumptions and any missing evidence. Do not include chain-of-thought.\n\n"
            + __import__("json").dumps(payload, ensure_ascii=False, default=str)
        )
        reservation = self.budget.reserve_call(role, MODEL_ALIAS, estimated_tokens=min(6000, max(2500, len(prompt) // 3)))
        if not reservation.allowed or not reservation.request_id:
            raise AnalysisBlocked(reservation.reason or "RouterAI budget denied this call")
        http_client = None
        try:
            llm_config = build_autogen_llm_config()
            http_client = llm_config["config_list"][0].get("http_client")
            try:
                from autogen import AssistantAgent, UserProxyAgent
            except ImportError as exc:
                raise AnalysisBlocked("The configured AG2/autogen package is not installed") from exc
            assistant = AssistantAgent(
                name="analysis_role",
                system_message=f"{ROLE_INSTRUCTIONS[role]}\n\n{SYSTEM_JSON_RULES}",
                llm_config=llm_config,
                human_input_mode="NEVER",
                max_consecutive_auto_reply=2,
            )
            executor_agent = UserProxyAgent(
                name="tool_executor",
                human_input_mode="NEVER",
                code_execution_config=False,
                max_consecutive_auto_reply=2,
            )
            if use_tools:
                register_tools(assistant, role, self.registry, self.tools, executor_agent)
            chat = executor_agent.initiate_chat(recipient=assistant, message=prompt, max_turns=3, clear_history=True)
            history = getattr(chat, "chat_history", []) or []
            raw = next((str(item.get("content", "")) for item in reversed(history)
                        if item.get("role") == "assistant" and item.get("content")), "")
            self.budget.record_usage(reservation.request_id, actual_tokens=None, actual_cost_rub=None)
            if http_client is not None:
                http_client.close()
            return {"role": role, "raw_json": raw, "model_alias": MODEL_ALIAS,
                    "tool_names": [spec.name for spec in self.registry.for_role(role)] if use_tools else []}
        except Exception:
            self.budget.record_usage(reservation.request_id, failed=True)
            if http_client is not None:
                http_client.close()
            raise
