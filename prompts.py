"""
System prompt builder for the AI Assistant.

Builds a dynamic system prompt per request including user info,
store config, active modules, setup state, and safety rules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select, func

if TYPE_CHECKING:
    from fastapi import Request


async def build_system_prompt(request: Request, context: str = "general") -> str:
    """Build the system prompt for the AI assistant."""
    from apps.configuration.models import HubConfig, StoreConfig

    db = request.state.db
    hub_id = request.state.hub_id

    hub_config = await HubConfig.get_config(db, hub_id)
    store_config = await StoreConfig.get_config(db, hub_id)

    user_name = getattr(request.state, "user_name", "User")
    user_role = getattr(request.state, "user_role", "employee")

    # Get active modules from registry
    registry = getattr(request.app.state, "module_registry", None)

    language = getattr(hub_config, "language", "en") if hub_config else "en"
    parts = [
        _base_instructions(language),
        _user_context(user_name, user_role),
        _store_context(store_config, hub_config),
        await _module_catalog(db),
        await _installed_module_contexts(db, hub_id, registry),
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
4. ONLY after the user confirms (says "sí", "confirmo", "adelante", "ok", "yes", "instala", "crea", "procede", "dale", "hazlo", etc.), execute ALL actions using your tool functions sequentially
5. After each tool execution, report briefly: ✓ Done / ✗ Failed

## CRITICAL: When the user request IS the confirmation — execute immediately

If the user's message is a direct imperative command with no ambiguity, DO NOT ask again.
Execute the tools right away without asking for confirmation:

- "instala los módulos X, Y, Z" → call execute(_modules, ModuleInstallerService, install) for each one immediately
- "instala X" → call execute(_modules, ModuleInstallerService, install) immediately
- "crea un empleado llamado X con rol Y" → call create_employee immediately
- "configura el negocio como X" → call update_store_config immediately
- "instala todos los módulos de [bloque]" → install them all immediately

A direct imperative command from the user IS their confirmation. Do not ask "¿Confirmo estas acciones?" — just execute.

## Installing modules

Use the generic `execute` tool with the `_modules` service:
- execute({{"module": "_modules", "service": "ModuleInstallerService", "action": "install", "args": {{"module_id": "customers"}}}})
- execute({{"module": "_modules", "service": "ModuleInstallerService", "action": "install", "args": {{"module_id": "inventory"}}}})
- execute({{"module": "_modules", "service": "ModuleInstallerService", "action": "install", "args": {{"module_id": "orders"}}}})

To enable a disabled module:
- execute({{"module": "_modules", "service": "ModuleInstallerService", "action": "enable", "args": {{"module_id": "customers"}}}})

To disable a module:
- execute({{"module": "_modules", "service": "ModuleInstallerService", "action": "disable", "args": {{"module_id": "customers"}}}})

For multiple modules, call `execute` once per module_id in sequence. If a module is already installed, the service reports it and you continue with the next one. Never stop mid-list.

## When executing (after confirmation or direct command)
- Call tool functions one by one, do not stop between them
- If a tool fails, report the error and continue with the next action
- After all actions are complete, give a summary of what was done

## When to skip confirmation entirely
- Simple questions ("what modules are available?") — answer directly with text
- Status queries ("show me the config") — answer directly with text
- Direct imperative commands (see above) — execute immediately

## Behavior
- Be concise. No long introductions.
- Always respond in the user's language.
- If the user gives you multiple tasks, group them in one plan and confirm once.
- Never get stuck in a confirmation loop. If you already asked once and the user said yes, execute."""


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
    """Return a compact text block listing active module names.

    Used by tests and lightweight callers that already have a list of
    module names and do not need the full DB-backed catalog.
    """
    if not module_names:
        return "## Active Modules\nNo modules installed yet."

    modules_list = ", ".join(module_names)
    return f"## Active Modules ({len(module_names)} installed)\n{modules_list}"


async def _module_catalog(db) -> str:
    """Compact catalog of ALL available modules for GPT to recommend installations."""
    from apps.system.models import HubModuleVersion

    # Get latest version of each module
    subq = (
        select(
            HubModuleVersion.module_id,
            func.max(HubModuleVersion.released_at).label("max_released"))
        .group_by(HubModuleVersion.module_id)
        .subquery()
    )
    result = await db.execute(
        select(HubModuleVersion)
        .join(
            subq,
            (HubModuleVersion.module_id == subq.c.module_id)
            & (HubModuleVersion.released_at == subq.c.max_released))
        .order_by(HubModuleVersion.module_id)
    )
    versions = result.scalars().all()

    if not versions:
        return "## Available Modules\nNo modules in catalog yet."

    lines = [
        "## Available Modules (install with execute(_modules, ModuleInstallerService, install))",
        "| ID | Description | Requires |",
        "|----|-------------|----------|",
    ]
    for v in versions:
        desc = (v.description or "")[:60].replace("|", "-").replace("\n", " ")
        deps = ", ".join(v.dependencies) if v.dependencies else "-"
        lines.append(f"| {v.module_id} | {desc} | {deps} |")

    return "\n".join(lines)


async def _installed_module_contexts(db, hub_id, registry) -> str:
    """Build module context for GPT from the service registry.

    Prefers live service registry context (auto-generated from
    ``@action``-decorated methods).  Falls back to the ``ai_context``
    text stored in the module catalog DB row.
    """
    from apps.system.models import HubModuleVersion
    from hotframe.apps.service_facade import generate_module_context

    if not registry:
        return "## Active Modules\nNo modules installed yet."

    menu_items = registry.get_menu_items()
    active_ids = [m.get("module_id") for m in menu_items if m.get("module_id")]

    if not active_ids:
        return "## Active Modules\nNo modules installed yet."

    # Fetch DB-stored ai_context as fallback for modules without services
    result = await db.execute(
        select(HubModuleVersion.module_id, HubModuleVersion.ai_context)
        .where(HubModuleVersion.module_id.in_(active_ids))
        .where(HubModuleVersion.ai_context != "")
        .where(HubModuleVersion.ai_context.isnot(None))
    )
    db_contexts = {row.module_id: row.ai_context for row in result.all()}

    parts = [f"## Active Modules ({len(active_ids)} installed)"]
    parts.append(
        "Use the **query** tool to read data and the **execute** tool to write data. "
        "Specify module, service, action, and args as shown below."
    )

    total_chars = 0
    MAX_CONTEXT_CHARS = 8000

    for mid in active_ids:
        # Prefer service registry context (live, from @action decorators)
        svc_ctx = generate_module_context(mid)
        if svc_ctx:
            header = f"## {mid}"
            block = f"{header}\n{svc_ctx}"
            if total_chars + len(block) < MAX_CONTEXT_CHARS:
                parts.append(block)
                total_chars += len(block)
                continue

        # Fallback to DB-stored ai_context
        db_ctx = db_contexts.get(mid, "")
        if db_ctx and total_chars < MAX_CONTEXT_CHARS:
            parts.append(db_ctx.strip())
            total_chars += len(db_ctx)
        else:
            parts.append(f"- {mid}: installed (no context available)")

    return "\n\n".join(parts)


def _setup_context(hub_config: object | None, store_config: object | None) -> str:
    from .config_state import (
        get_selected_blocks,
        get_selected_sectors,
        get_sales_profile,
        get_region)

    steps = []

    language = getattr(hub_config, "language", "") if hub_config else ""
    country = getattr(hub_config, "country_code", "") if hub_config else ""

    if language and country:
        steps.append(f"Step 1 (Regional): COMPLETE — language={language}, country={country}")
    else:
        steps.append("Step 1 (Regional): PENDING — set language, country, timezone, currency")

    sectors = get_selected_sectors(hub_config) if hub_config else []
    business_types = get_selected_blocks(hub_config) if hub_config else []
    sales = get_sales_profile(hub_config) if hub_config else {"sells_b2b": True, "sells_b2c": True}
    region = get_region(hub_config) if hub_config else ""

    profile_parts = []
    if sectors:
        profile_parts.append(f"sectors={sectors}")
    if business_types:
        profile_parts.append(f"business_types={business_types}")
    if region:
        profile_parts.append(f"region={region}")
    profile_parts.append(f"sells_b2b={sales['sells_b2b']}")
    profile_parts.append(f"sells_b2c={sales['sells_b2c']}")

    if sectors or business_types:
        steps.append(f"Step 2 (Business profile): COMPLETE — {', '.join(profile_parts)}")
    else:
        steps.append("Step 2 (Business profile): PENDING — ask the user about sector, type, B2B/B2C")

    biz_name = getattr(store_config, "business_name", "") if store_config else ""
    vat = getattr(store_config, "vat_number", "") if store_config else ""
    if biz_name and vat:
        steps.append(f"Step 3 (Business identity): COMPLETE — {biz_name}")
    else:
        steps.append("Step 3 (Business identity): PENDING — set business name, address, VAT")

    is_configured = getattr(store_config, "is_configured", False) if store_config else False
    if is_configured:
        steps.append("Step 4 (Tax): COMPLETE")
    else:
        steps.append("Step 4 (Tax): PENDING — configure tax rate")

    steps_text = "\n".join(f"- {s}" for s in steps)

    return f"""## Setup Wizard Status
You are helping the user set up their hub for the first time.
Guide them through the configuration process.

{steps_text}

## Tools for setup
- Use `get_compliance_modules` to know what legal modules the user needs — NEVER guess VAT rates, invoicing laws, or country-specific obligations from memory.
- Use `get_recommended_modules` to suggest modules by sector/business_type — NEVER invent module names.
- Use `list_sector_assets` when you need the raw asset inventory.
- Use `draft_products_for_business` to get a starter product catalog (name/price/tax/image) for the user's business types. Present it for review; do not write to DB yourself. Writing happens via module services (e.g., sales.ProductService) through the generic execute tool.

Ask the user about their business: sector (hospitality, retail...), type (bar, restaurant...), country, region (e.g. "País Vasco"), whether they sell to businesses (B2B), consumers (B2C), or both.
Based on their answer, call the catalog/compliance tools and present results grounded in real data."""


def _safety_rules() -> str:
    return """## Safety Rules
1. NEVER modify data without using the appropriate tool
2. All write operations require user confirmation before execution
3. Respect user permissions - only use tools the user has access to
4. If unsure about what the user wants, ask for clarification
5. When creating bulk data (products, employees), confirm the full list before executing
6. Never expose sensitive data (PINs, tokens, API keys)
7. If an operation fails, explain what went wrong and suggest alternatives"""
