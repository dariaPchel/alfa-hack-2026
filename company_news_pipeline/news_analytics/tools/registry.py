"""Framework-independent role-to-tool catalog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Type

from pydantic import BaseModel


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    purpose: str
    request_model: Type[BaseModel]
    response_model: Type[BaseModel] | None
    handler: Callable[..., Any]
    roles: frozenset[str]
    timeout_seconds: float = 20.0
    retries: int = 0
    provenance_required: bool = True


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Duplicate tool name: {spec.name}")
        if not spec.roles:
            raise ValueError(f"Tool {spec.name} has no role grants")
        if spec.timeout_seconds <= 0 or spec.retries < 0:
            raise ValueError(f"Invalid execution policy for {spec.name}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def for_role(self, role: str) -> list[ToolSpec]:
        return sorted((spec for spec in self._specs.values() if role in spec.roles), key=lambda spec: spec.name)

    def catalog(self, role: str) -> list[dict[str, Any]]:
        return [{"name": spec.name, "version": spec.version, "purpose": spec.purpose,
                 "input_schema": spec.request_model.model_json_schema(),
                 "timeout_seconds": spec.timeout_seconds, "retries": spec.retries}
                for spec in self.for_role(role)]
