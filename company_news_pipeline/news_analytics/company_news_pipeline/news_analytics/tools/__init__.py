"""Typed, role-scoped tool execution for news analysis agents."""

from .executor import ToolExecutor
from .registry import ToolRegistry, ToolSpec

__all__ = ["ToolExecutor", "ToolRegistry", "ToolSpec"]
