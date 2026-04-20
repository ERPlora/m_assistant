MODULE_ID = "assistant"
MODULE_NAME = "AI Assistant"
MODULE_VERSION = "1.8.1"
MODULE_ICON = "sparkles-outline"
MODULE_DESCRIPTION = "AI-powered business assistant with contextual tools for inventory, sales, customers, invoicing, and more. Supports voice input and tiered subscription plans."
MODULE_AUTHOR = "ERPlora"
MODULE_FUNCTIONS = ["utility", "ai"]
MODULE_COLOR = "#7c3aed"

HAS_MODELS = True
MIDDLEWARE = ""

MENU = {
    "label": "AI Assistant",
    "icon": "sparkles-outline",
    "order": 99,
}

NAVIGATION = [
    {"id": "chat", "label": "Chat", "icon": "chatbubbles-outline", "view": "chat"},
    {"id": "history", "label": "History", "icon": "time-outline", "view": "history"},
    {"id": "logs", "label": "Action Log", "icon": "list-outline", "view": "logs"},
]

DEPENDENCIES: list[str] = []

PERMISSIONS = [
    ("use_chat", "Use the AI chat"),
    ("use_setup_mode", "Configure hub during setup"),
    ("view_logs", "View action logs"),
    ("manage_settings", "Manage assistant settings"),
]

ROLE_PERMISSIONS = {
    "admin": ["*"],
    "manager": ["use_chat", "view_logs"],
    "employee": ["use_chat"],
}

SCHEDULED_TASKS: list[dict] = []

PRICING = {
    "type": "subscription",
    "subscription_price_monthly": 5.00,
}

FREE_TIER_LIMITS = {
    "messages_per_month": 30,
}


# ---------------------------------------------------------------------------
# New contract (Sprint 4): ModuleConfig equivalent.
# The legacy module-level constants above are still read by the current
# manifest loader; this class exposes the Django-like ModuleConfig contract
# for the new runtime/apps registry.
# ---------------------------------------------------------------------------

from hotframe.apps import ModuleConfig


class AssistantModule(ModuleConfig):
    """AI Assistant — system module, always active, ships with Docker image."""

    name = MODULE_ID
    verbose_name = MODULE_NAME
    version = MODULE_VERSION
    is_system = True  # CRITICAL: cannot be deactivated or uninstalled
    requires_restart = False

    async def ready(self) -> None:
        return None
