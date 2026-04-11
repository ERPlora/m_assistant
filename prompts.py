"""
System prompt builder for the AI Assistant.

Builds a dynamic system prompt per request including user info,
store config, active modules, setup state, and safety rules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request


async def build_system_prompt(request: Request, context: str = "general") -> str:
    """Build the system prompt for the AI assistant."""
    from app.apps.configuration.models import HubConfig, StoreConfig

    db = request.state.db
    hub_id = request.state.hub_id

    hub_config = await HubConfig.get_config(db, hub_id)
    store_config = await StoreConfig.get_config(db, hub_id)

    user_name = getattr(request.state, "user_name", "User")
    user_role = getattr(request.state, "user_role", "employee")

    # Get active modules from registry
    registry = getattr(request.app.state, "module_registry", None)
    module_names = []
    if registry:
        menu_items = registry.get_menu_items()
        module_names = [item.get("label", item.get("module_id", "")) for item in menu_items]

    language = getattr(hub_config, "language", "en") if hub_config else "en"
    parts = [
        _base_instructions(language),
        _user_context(user_name, user_role),
        _store_context(store_config, hub_config),
        _modules_context(module_names),
    ]

    if context == "setup":
        parts.append(_setup_context(hub_config, store_config))

    parts.append(_safety_rules())

    return "\n\n".join(parts)


def _base_instructions(language: str) -> str:
    lang_name = {
        "en": "English", "es": "Spanish", "de": "German",
        "fr": "French", "it": "Italian", "pt": "Portuguese",
    }.get(language, "English")

    return f"""You are an AI assistant for ERPlora, a modular POS/ERP system.
You help users configure their hub, manage products, employees, and business operations.
Always respond in {lang_name}.

## How to handle user requests

When the user describes their business or asks you to configure something:
1. Analyze what they need (modules, business info, employees, tax classes, etc.)
2. Present a clear, numbered plan of ALL actions you will take
3. Ask the user to confirm: "¿Confirmo estas acciones?"
4. ONLY after the user confirms (says "sí", "confirmo", "adelante", "ok", "yes", etc.), execute ALL actions using your tool functions sequentially
5. After each tool execution, report briefly: ✓ Done / ✗ Failed

## When executing (after confirmation)
- Call tool functions one by one, do not stop between them
- If a tool fails, report the error and continue with the next action
- After all actions are complete, give a summary of what was done

## When to skip confirmation
- Simple questions ("what modules are available?") — answer directly with text
- Status queries ("show me the config") — answer directly with text

## Behavior
- Be concise. No long introductions.
- Always respond in the user's language.
- If the user gives you multiple tasks, group them in one plan and confirm once."""


def _user_context(user_name: str, user_role: str) -> str:
    return f"""## Current User
- Name: {user_name}
- Role: {user_role}"""


def _store_context(store_config: object | None, hub_config: object | None) -> str:
    if not store_config or not hub_config:
        return "## Store Configuration\n(Not configured yet)"

    text = f"""## Store Configuration
- Business: {getattr(store_config, 'business_name', '') or '(not set)'}
- Currency: {getattr(hub_config, 'currency', 'EUR')}
- Language: {getattr(hub_config, 'language', 'en')}
- Country: {getattr(hub_config, 'country_code', '') or '(not set)'}
- Tax rate: {getattr(store_config, 'tax_rate', 0)}%
- Tax included in prices: {'Yes' if getattr(store_config, 'tax_included', False) else 'No'}"""

    vat = getattr(store_config, "vat_number", "")
    if vat:
        text += f"\n- VAT/Tax ID: {vat}"

    return text


def _modules_context(module_names: list[str]) -> str:
    if not module_names:
        return "## Active Modules\nNo modules installed yet."

    modules_list = ", ".join(module_names)
    return f"""## Active Modules ({len(module_names)} installed)
{modules_list}"""


def _setup_context(hub_config: object | None, store_config: object | None) -> str:
    steps = []

    language = getattr(hub_config, "language", "") if hub_config else ""
    country = getattr(hub_config, "country_code", "") if hub_config else ""

    if language and country:
        steps.append("Step 1 (Regional): COMPLETE")
    else:
        steps.append("Step 1 (Regional): PENDING - set language, country, timezone, currency")

    selected = getattr(hub_config, "selected_business_types", []) if hub_config else []
    if selected:
        blocks = ", ".join(selected)
        steps.append(f"Step 2 (Modules): COMPLETE - selected: {blocks}")
    else:
        steps.append("Step 2 (Modules): PENDING - select functional blocks for business type")

    biz_name = getattr(store_config, "business_name", "") if store_config else ""
    vat = getattr(store_config, "vat_number", "") if store_config else ""
    if biz_name and vat:
        steps.append(f"Step 3 (Business): COMPLETE - {biz_name}")
    else:
        steps.append("Step 3 (Business): PENDING - set business name, address, VAT")

    is_configured = getattr(store_config, "is_configured", False) if store_config else False
    if is_configured:
        steps.append("Step 4 (Tax): COMPLETE")
    else:
        steps.append("Step 4 (Tax): PENDING - configure tax rate")

    steps_text = "\n".join(f"- {s}" for s in steps)

    return f"""## Setup Wizard Status
You are helping the user set up their hub for the first time.
Guide them through the configuration process.

{steps_text}

Ask the user about their business type and location.
Based on their answer, recommend appropriate functional blocks and configure settings."""


def _safety_rules() -> str:
    return """## Safety Rules
1. NEVER modify data without using the appropriate tool
2. All write operations require user confirmation before execution
3. Respect user permissions - only use tools the user has access to
4. If unsure about what the user wants, ask for clarification
5. When creating bulk data (products, employees), confirm the full list before executing
6. Never expose sensitive data (PINs, tokens, API keys)
7. If an operation fails, explain what went wrong and suggest alternatives"""
