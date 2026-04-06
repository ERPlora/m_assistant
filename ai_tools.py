"""
Assistant module AI tools.

The assistant module's own tools are registered in tools/hub_tools.py and
tools/setup_tools.py.  This file exists to conform to the standard module
interface (every module with AI integration exposes ai_tools.py) but
delegates to the sub-packages.

Importing this module triggers @register_tool decorators in hub_tools
and setup_tools.
"""

from assistant.tools import hub_tools as _hub_tools  # noqa: F401
from assistant.tools import setup_tools as _setup_tools  # noqa: F401
