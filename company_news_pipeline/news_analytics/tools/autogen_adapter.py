"""AG2 registration adapter for only the tools assigned to a given role."""

from __future__ import annotations

import inspect
from typing import Any

from .executor import ToolExecutor
from .registry import ToolRegistry


def register_tools(agent: Any, role: str, registry: ToolRegistry, executor: ToolExecutor,
                   executor_agent: Any) -> list[str]:
    """Register tools with the existing AG2 register_function API family."""

    try:
        from autogen import register_function
    except ImportError as exc:
        raise RuntimeError("Install the repository's pinned AG2/autogen dependency") from exc

    registered = []
    for spec in registry.for_role(role):
        def invoke(_tool_name=spec.name, **kwargs):
            return executor.execute(role, _tool_name, kwargs).model_dump_json()

        invoke.__name__ = spec.name
        invoke.__doc__ = spec.purpose
        parameters = []
        for field_name, field in spec.request_model.model_fields.items():
            default = inspect.Parameter.empty if field.is_required() else field.default
            parameters.append(inspect.Parameter(field_name, inspect.Parameter.KEYWORD_ONLY,
                                                default=default, annotation=field.annotation))
        invoke.__signature__ = inspect.Signature(parameters)  # type: ignore[attr-defined]
        register_function(invoke, caller=agent, executor=executor_agent, description=spec.purpose)
        registered.append(spec.name)
    return registered
