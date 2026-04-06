"""
Assistant tool exports.

Re-exports from app.ai.registry for backward compatibility
with the hub_tools/setup_tools import pattern.
"""

from app.ai.registry import (
    AssistantTool,
    TOOL_REGISTRY,
    register_tool,
    get_tools_for_user,
    tools_to_openai_schema,
)

__all__ = [  # noqa: RUF022
    "AssistantTool",
    "TOOL_REGISTRY",
    "register_tool",
    "get_tools_for_user",
    "tools_to_openai_schema",
]
