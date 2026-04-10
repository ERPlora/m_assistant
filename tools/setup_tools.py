"""
Setup Wizard Tools — only available in setup context.
"""

from __future__ import annotations

from typing import Any

from app.ai.registry import AssistantTool, register_tool
from app.core.db.transactions import atomic


@register_tool
class SetRegionalConfig(AssistantTool):
    name = "set_regional_config"
    description = "Set regional configuration: language, timezone, country code, currency"
    # requires_confirmation removed — system prompt controls when to ask
    required_permission = "assistant.use_setup_mode"
    setup_only = True
    parameters = {
        "type": "object",
        "properties": {
            "language": {"type": ["string", "null"], "description": "Language code (e.g., 'en', 'es')"},
            "timezone": {"type": ["string", "null"], "description": "Timezone (e.g., 'Europe/Madrid')"},
            "country_code": {"type": ["string", "null"], "description": "ISO country code (e.g., 'ES')"},
            "currency": {"type": ["string", "null"], "description": "ISO currency code (e.g., 'EUR')"},
        },
        "required": ["language", "timezone", "country_code", "currency"],
        "additionalProperties": False,
    }

    async def execute(self, args: dict, request: Any) -> dict:
        from app.apps.configuration.models import HubConfig
        async with atomic(request.state.db) as session:
            config = await HubConfig.get_config(session, request.state.hub_id)
            if not config:
                return {"error": "Hub config not found"}
            updated = []
            for field in ["language", "timezone", "country_code", "currency"]:
                value = args.get(field)
                if value is not None:
                    setattr(config, field, value)
                    updated.append(field)
        return {"success": True, "updated_fields": updated}


@register_tool
class SetBusinessInfo(AssistantTool):
    name = "set_business_info"
    description = "Set business information: name, address, VAT/tax ID"
    # requires_confirmation removed — system prompt controls when to ask
    required_permission = "assistant.use_setup_mode"
    setup_only = True
    parameters = {
        "type": "object",
        "properties": {
            "business_name": {"type": "string", "description": "Business name"},
            "business_address": {"type": "string", "description": "Business address"},
            "vat_number": {"type": "string", "description": "VAT/Tax ID"},
        },
        "required": ["business_name", "business_address", "vat_number"],
        "additionalProperties": False,
    }

    async def execute(self, args: dict, request: Any) -> dict:
        from app.apps.configuration.models import StoreConfig
        async with atomic(request.state.db) as session:
            store = await StoreConfig.get_config(session, request.state.hub_id)
            if not store:
                return {"error": "Store config not found"}
            store.business_name = args["business_name"]
            store.business_address = args["business_address"]
            store.vat_number = args["vat_number"]
        return {"success": True, "business_name": args["business_name"]}


@register_tool
class SetTaxConfig(AssistantTool):
    name = "set_tax_config"
    description = "Set tax configuration: default tax rate and whether prices include tax"
    # requires_confirmation removed — system prompt controls when to ask
    required_permission = "assistant.use_setup_mode"
    setup_only = True
    parameters = {
        "type": "object",
        "properties": {
            "tax_rate": {"type": "number", "description": "Default tax rate percentage"},
            "tax_included": {"type": "boolean", "description": "Whether prices include tax"},
        },
        "required": ["tax_rate", "tax_included"],
        "additionalProperties": False,
    }

    async def execute(self, args: dict, request: Any) -> dict:
        from app.apps.configuration.models import StoreConfig
        async with atomic(request.state.db) as session:
            store = await StoreConfig.get_config(session, request.state.hub_id)
            if not store:
                return {"error": "Store config not found"}
            store.tax_rate = args["tax_rate"]
            store.tax_included = args["tax_included"]
            store.is_configured = True
        return {"success": True, "tax_rate": str(args["tax_rate"]), "tax_included": args["tax_included"]}


@register_tool
class CompleteSetupStep(AssistantTool):
    name = "complete_setup_step"
    description = "Mark the hub setup as complete"
    # requires_confirmation removed — system prompt controls when to ask
    required_permission = "assistant.use_setup_mode"
    setup_only = True
    parameters = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}

    async def execute(self, args: dict, request: Any) -> dict:
        from app.apps.configuration.models import HubConfig, StoreConfig
        async with atomic(request.state.db) as session:
            hub_config = await HubConfig.get_config(session, request.state.hub_id)
            store_config = await StoreConfig.get_config(session, request.state.hub_id)
            if hub_config:
                hub_config.is_configured = True
            if store_config:
                store_config.is_configured = True
        return {"success": True, "message": "Setup completed. Hub is now fully configured."}
