"""
Hub Core Tools — always available.

These tools operate on the Hub's core configuration: HubConfig, StoreConfig,
TaxClass, modules, roles, and employees.
"""

from __future__ import annotations

from typing import Any

import httpx

from apps.ai.registry import AssistantTool, register_tool
from hotframe.models.queryset import HubQuery
from hotframe.orm.transactions import atomic

from ..config_state import get_primary_selected_block, get_selected_blocks, set_selected_blocks


# ============================================================================
# READ TOOLS
# ============================================================================


@register_tool
class GetHubConfig(AssistantTool):
    name = "get_hub_config"
    description = "Get current hub configuration: language, currency, timezone, country, theme, dark mode"
    parameters = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}

    async def execute(self, args: dict, request: Any) -> dict:
        from apps.configuration.models import HubConfig
        config = await HubConfig.get_config(request.state.db, request.state.hub_id)
        if not config:
            return {"error": "Hub config not found"}
        return {
            "language": config.language,
            "currency": config.currency,
            "timezone": config.timezone,
            "country_code": config.country_code,
            "color_theme": getattr(config, "color_theme", ""),
            "dark_mode": getattr(config, "dark_mode", False),
            "is_configured": config.is_configured,
        }


@register_tool
class GetStoreConfig(AssistantTool):
    name = "get_store_config"
    description = "Get store/business configuration: name, address, VAT, phone, email, tax settings"
    parameters = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}

    async def execute(self, args: dict, request: Any) -> dict:
        from apps.configuration.models import StoreConfig
        store = await StoreConfig.get_config(request.state.db, request.state.hub_id)
        if not store:
            return {"error": "Store config not found"}
        return {
            "business_name": getattr(store, "store_name", "") or "",
            "business_address": getattr(store, "address", "") or "",
            "vat_number": getattr(store, "tax_number", "") or "",
            "phone": getattr(store, "phone", "") or "",
            "email": getattr(store, "email", "") or "",
            "tax_rate": str(getattr(store, "tax_rate", 0)),
            "tax_included": getattr(store, "tax_included", False),
        }


@register_tool
class ListAvailableBlocks(AssistantTool):
    name = "list_available_blocks"
    description = "List all available functional blocks from Cloud marketplace"
    parameters = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}

    async def execute(self, args: dict, request: Any) -> dict:
        from apps.configuration.models import HubConfig
        config = await HubConfig.get_config(request.state.db, request.state.hub_id)
        cloud_url = getattr(config, "cloud_api_url", "https://erplora.com") if config else "https://erplora.com"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{cloud_url}/api/v1/marketplace/solutions/")
                if resp.status_code == 200:
                    blocks = resp.json()
                    items = blocks if isinstance(blocks, list) else blocks.get("results", [])
                    return {
                        "blocks": [
                            {"slug": b.get("slug", ""), "name": b.get("name", ""), "tagline": b.get("tagline", "")}
                            for b in items
                        ]
                    }
                return {"error": f"Cloud API returned {resp.status_code}"}
        except Exception as e:
            return {"error": f"Failed to fetch blocks: {e!s}"}


@register_tool
class GetSelectedBlocks(AssistantTool):
    name = "get_selected_blocks"
    description = "Get the functional blocks currently selected for this hub"
    parameters = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}

    async def execute(self, args: dict, request: Any) -> dict:
        from apps.configuration.models import HubConfig
        config = await HubConfig.get_config(request.state.db, request.state.hub_id)
        if not config:
            return {"selected_blocks": [], "solution_slug": ""}
        return {
            "selected_blocks": get_selected_blocks(config),
            "solution_slug": get_primary_selected_block(config),
        }


@register_tool
class ListModules(AssistantTool):
    name = "list_modules"
    description = "List all installed and active modules on this hub"
    parameters = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}

    async def execute(self, args: dict, request: Any) -> dict:
        registry = getattr(request.app.state, "module_registry", None)
        if not registry:
            return {"modules": [], "total": 0}
        menu_items = registry.get_menu_items()
        return {
            "modules": [
                {"module_id": item.get("module_id", ""), "label": str(item.get("label", "")), "icon": item.get("icon", "")}
                for item in menu_items
            ],
            "total": len(menu_items),
        }


@register_tool
class ListRoles(AssistantTool):
    name = "list_roles"
    description = "List all roles with their permissions summary"
    parameters = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}

    async def execute(self, args: dict, request: Any) -> dict:
        from apps.auth.models import Role
        query = HubQuery(Role, request.state.db, request.state.hub_id)
        roles = await query.filter(Role.is_active == True).order_by(Role.name).all()  # noqa: E712
        return {
            "roles": [
                {"id": str(r.id), "name": r.name, "display_name": getattr(r, "display_name", r.name), "source": getattr(r, "source", "custom")}
                for r in roles
            ]
        }


@register_tool
class ListEmployees(AssistantTool):
    name = "list_employees"
    description = "List all employees/users on this hub"
    parameters = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}

    async def execute(self, args: dict, request: Any) -> dict:
        from apps.auth.models import LocalUser
        query = HubQuery(LocalUser, request.state.db, request.state.hub_id)
        users = await query.filter(LocalUser.is_active == True).order_by(LocalUser.name).all()  # noqa: E712
        return {
            "employees": [
                {"id": str(u.id), "name": u.name, "email": getattr(u, "email", ""), "role": getattr(u, "role", "")}
                for u in users
            ]
        }


@register_tool
class ListTaxClasses(AssistantTool):
    name = "list_tax_classes"
    description = "List all tax classes/rates configured on this hub"
    parameters = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}

    async def execute(self, args: dict, request: Any) -> dict:
        from apps.configuration.models import TaxClass
        query = HubQuery(TaxClass, request.state.db, request.state.hub_id)
        tax_classes = await query.filter(TaxClass.is_active == True).all()  # noqa: E712
        return {
            "tax_classes": [
                {"id": str(tc.id), "name": tc.name, "rate": str(tc.rate), "is_default": getattr(tc, "is_default", False)}
                for tc in tax_classes
            ]
        }


# ============================================================================
# WRITE TOOLS (require confirmation)
# ============================================================================


@register_tool
class UpdateStoreConfig(AssistantTool):
    name = "update_store_config"
    description = "Update store/business configuration. Only include fields you want to change."
    required_permission = "assistant.use_chat"
    parameters = {
        "type": "object",
        "properties": {
            "business_name": {"type": "string", "description": "Business name"},
            "business_address": {"type": "string", "description": "Business address"},
            "vat_number": {"type": "string", "description": "VAT/Tax ID number (NIF/CIF)"},
            "phone": {"type": "string", "description": "Phone number"},
            "email": {"type": "string", "description": "Email address"},
            "tax_rate": {"type": "number", "description": "Default tax rate percentage"},
            "tax_included": {"type": "boolean", "description": "Whether prices include tax"},
        },
        "required": [],
        "additionalProperties": False,
    }

    # Map tool parameter names → DB column names
    _FIELD_MAP = {
        "business_name": "store_name",
        "business_address": "address",
        "vat_number": "tax_number",
        "phone": "phone",
        "email": "email",
        "tax_rate": "tax_rate",
        "tax_included": "tax_included",
    }

    async def execute(self, args: dict, request: Any) -> dict:
        from apps.configuration.models import StoreConfig
        from hotframe.config.database import get_session_factory
        factory = get_session_factory()
        async with factory() as session:
            session.info["hub_id"] = request.state.hub_id
            store = await StoreConfig.get_config(session, request.state.hub_id)
            if not store:
                return {"error": "Store config not found"}
            updated = []
            for param_name, db_field in self._FIELD_MAP.items():
                value = args.get(param_name)
                if value is not None:
                    setattr(store, db_field, value)
                    updated.append(param_name)
            await session.commit()
        return {"success": True, "updated_fields": updated}


@register_tool
class SelectBlocks(AssistantTool):
    name = "select_blocks"
    description = "Select functional blocks for this hub"
    # requires_confirmation removed — system prompt controls when to ask
    required_permission = "assistant.use_setup_mode"
    parameters = {
        "type": "object",
        "properties": {
            "block_slugs": {"type": "array", "items": {"type": "string"}, "description": "List of block slugs"},
        },
        "required": ["block_slugs"],
        "additionalProperties": False,
    }

    async def execute(self, args: dict, request: Any) -> dict:
        from apps.configuration.models import HubConfig
        async with atomic(request.state.db) as session:
            config = await HubConfig.get_config(session, request.state.hub_id)
            if not config:
                return {"error": "Hub config not found"}
            block_slugs = set_selected_blocks(config, args.get("block_slugs", []))
        return {"success": True, "selected_blocks": block_slugs, "count": len(block_slugs)}


@register_tool
class CreateRole(AssistantTool):
    name = "create_role"
    description = "Create a custom role with specific permission wildcards"
    # requires_confirmation removed — system prompt controls when to ask
    required_permission = "assistant.use_setup_mode"
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Role name"},
            "display_name": {"type": "string", "description": "Display name"},
            "description": {"type": "string", "description": "Role description"},
            "wildcards": {"type": "array", "items": {"type": "string"}, "description": "Permission wildcards"},
        },
        "required": ["name", "display_name", "description", "wildcards"],
        "additionalProperties": False,
    }

    async def execute(self, args: dict, request: Any) -> dict:
        from apps.auth.models import Role
        async with atomic(request.state.db) as session:
            role = Role(
                hub_id=request.state.hub_id,
                name=args["name"],
                display_name=args["display_name"],
                description=args.get("description", ""),
                source="custom",
                is_system=False)
            session.add(role)
            await session.flush()
            return {"success": True, "role_id": str(role.id), "name": role.name}


@register_tool
class CreateEmployee(AssistantTool):
    name = "create_employee"
    description = "Create a new local employee"
    # requires_confirmation removed — system prompt controls when to ask
    required_permission = "assistant.use_setup_mode"
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Employee full name"},
            "email": {"type": "string", "description": "Employee email"},
            "pin": {"type": "string", "description": "4-digit PIN code"},
            "role_name": {"type": "string", "description": "Role name to assign"},
        },
        "required": ["name", "email", "pin", "role_name"],
        "additionalProperties": False,
    }

    async def execute(self, args: dict, request: Any) -> dict:
        from apps.auth.models import LocalUser, Role
        from hotframe.auth.auth import hash_pin
        async with atomic(request.state.db) as session:
            # Look up Role by name to get role_id
            role_name = args.get("role_name", "employee")
            role_query = HubQuery(Role, session, request.state.hub_id)
            role_obj = await role_query.filter(Role.name == role_name, Role.is_active == True).first()  # noqa: E712
            role_id = role_obj.id if role_obj else None

            user = LocalUser(
                hub_id=request.state.hub_id,
                name=args["name"],
                email=args["email"],
                pin_hash=hash_pin(args["pin"]),
                role_id=role_id)
            session.add(user)
            await session.flush()
            return {"success": True, "employee_id": str(user.id), "name": user.name, "role": role_name}


@register_tool
class CreateTaxClass(AssistantTool):
    name = "create_tax_class"
    description = "Create a new tax class/rate (e.g., 'IVA General 21%', 'IGIC 7%')"
    # requires_confirmation removed — system prompt controls when to ask
    required_permission = "assistant.use_setup_mode"
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Tax class name (e.g., 'IVA General 21%')"},
            "rate": {"type": "number", "description": "Tax rate as percentage (e.g., 21.0)"},
            "description": {"type": "string", "description": "Optional description"},
            "is_default": {"type": "boolean", "description": "Whether this is the default tax class"},
        },
        "required": ["name", "rate"],
        "additionalProperties": False,
    }

    async def execute(self, args: dict, request: Any) -> dict:
        from apps.configuration.models import TaxClass
        async with atomic(request.state.db) as session:
            if args.get("is_default"):
                # Clear existing defaults
                query = HubQuery(TaxClass, session, request.state.hub_id)
                defaults = await query.filter(TaxClass.is_default == True).all()  # noqa: E712
                for tc in defaults:
                    tc.is_default = False

            tc = TaxClass(
                hub_id=request.state.hub_id,
                name=args["name"],
                rate=args["rate"],
                is_default=args.get("is_default", False))
            session.add(tc)
            await session.flush()
            return {"success": True, "tax_class_id": str(tc.id), "name": tc.name, "rate": str(tc.rate)}


# InstallModule, EnableModule, DisableModule removed.
# Module management is now handled by ModuleInstallerService in
# app/apps/main/services.py (registered as _modules core service).
# Use the generic execute() tool:
#   execute(_modules, ModuleInstallerService, install, {"module_id": "customers"})
#   execute(_modules, ModuleInstallerService, enable, {"module_id": "customers"})
#   execute(_modules, ModuleInstallerService, disable, {"module_id": "customers"})
