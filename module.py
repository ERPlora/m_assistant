MODULE_ID = "assistant"
MODULE_NAME = "AI Assistant"
MODULE_VERSION = "1.7.3"
MODULE_ICON = "sparkles-outline"
MODULE_DESCRIPTION = "AI-powered business assistant with contextual tools for inventory, sales, customers, invoicing, and more. Supports voice input and tiered subscription plans."
MODULE_AUTHOR = "ERPlora"
MODULE_CATEGORY = "utility"
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
