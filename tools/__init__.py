"""
Assistant tool exports.

Re-exports from apps.ai.registry for hub_tools/setup_tools/catalog_tools.

Importing this package triggers @register_tool decorators in all tool
sub-modules, populating TOOL_REGISTRY before the first request.
"""

from apps.ai.registry import (
    AssistantTool,
    TOOL_REGISTRY,
    register_tool,
    get_tools_for_user,
    tools_to_openai_schema)

# Import tool modules to trigger @register_tool decorators at import time.
from . import hub_tools as hub_tools
from . import setup_tools as setup_tools
from . import catalog_tools as catalog_tools
from . import product_tools as product_tools

__all__ = [  # noqa: RUF022
    "AssistantTool",
    "TOOL_REGISTRY",
    "register_tool",
    "get_tools_for_user",
    "tools_to_openai_schema",
    "hub_tools",
    "setup_tools",
    "catalog_tools",
    "product_tools",
]
