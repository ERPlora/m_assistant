"""
Catalog + Compliance tools: read-only queries to Cloud catalog API.

These tools give the assistant deterministic access to the canonical
catalog (sectors, business types, modules) and compliance requirements.
The assistant MUST use these instead of guessing about modules or fiscal
obligations.
"""
from __future__ import annotations

import logging
from typing import Any

from apps.ai.registry import AssistantTool, register_tool

logger = logging.getLogger(__name__)


async def _cloud_get(path: str, params: dict[str, Any] | None = None) -> Any:
    """Shared helper: GET from Cloud via the global CloudClient."""
    from apps.shared.services.cloud_client import _client_instance
    cloud = _client_instance
    if not cloud:
        logger.warning("CloudClient not initialized; catalog tools return empty")
        return None
    try:
        return await cloud.get(path, params=params)
    except Exception as e:
        logger.warning("Cloud GET %s failed: %s", path, e)
        return None


@register_tool
class GetRecommendedModules(AssistantTool):
    name = "get_recommended_modules"
    description = (
        "Return the list of ERPlora modules compatible with the given sectors "
        "and business types. Use this to recommend modules to the user — "
        "NEVER invent module names."
    )
    parameters = {
        "type": "object",
        "properties": {
            "sectors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of sector codes (e.g., ['hospitality'])",
            },
            "business_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of business type codes (e.g., ['bar', 'restaurant'])",
            },
            "functional_unit": {
                "type": ["string", "null"],
                "description": "Optional UFO code filter (e.g., 'FIN', 'RRH')",
            },
            "q": {
                "type": ["string", "null"],
                "description": "Optional free-text search",
            },
        },
        "required": ["sectors", "business_types", "functional_unit", "q"],
        "additionalProperties": False,
    }

    async def execute(self, args: dict, request: Any) -> dict:
        params: dict[str, Any] = {}
        sectors = args.get("sectors") or []
        business_types = args.get("business_types") or []
        if sectors:
            params["sectors"] = ",".join(sectors)
        if business_types:
            params["business_types"] = ",".join(business_types)
        fu = args.get("functional_unit")
        if fu:
            params["functional_unit"] = fu
        q = args.get("q")
        if q:
            params["q"] = q
        data = await _cloud_get("/api/v1/catalog/modules/", params or None)
        if data is None:
            return {"error": "Cloud unavailable", "modules": []}
        modules = (
            data if isinstance(data, list)
            else data.get("results", []) if isinstance(data, dict)
            else []
        )
        return {
            "count": len(modules),
            "modules": [
                {
                    "module_id": m.get("module_id"),
                    "name": m.get("name"),
                    "description": m.get("description"),
                    "functional_unit": m.get("functional_unit"),
                    "module_type": m.get("module_type"),
                }
                for m in modules
            ],
        }


@register_tool
class GetComplianceModules(AssistantTool):
    name = "get_compliance_modules"
    description = (
        "Return published ERPlora modules with functional_unit=COMP "
        "(compliance & legal) that apply to the given country. Use this "
        "when the user asks about legal/fiscal requirements — never guess "
        "or invent module names from memory."
    )
    parameters = {
        "type": "object",
        "properties": {
            "country": {"type": "string", "description": "ISO-2 country code (e.g., 'ES')"},
        },
        "required": ["country"],
        "additionalProperties": False,
    }

    async def execute(self, args: dict, request: Any) -> dict:
        country = (args.get("country") or "").upper()
        if not country:
            return {"error": "country required", "modules": []}
        data = await _cloud_get("/api/v1/catalog/compliance-modules/", {"country": country})
        if data is None:
            return {"error": "Cloud unavailable", "modules": []}
        modules = (
            data if isinstance(data, list)
            else data.get("results", []) if isinstance(data, dict)
            else []
        )
        return {
            "country": country,
            "count": len(modules),
            "modules": [
                {
                    "module_id": m.get("module_id"),
                    "name": m.get("name"),
                    "description": m.get("description"),
                    "module_type": m.get("module_type"),
                }
                for m in modules
            ],
        }


@register_tool
class ListSectorAssets(AssistantTool):
    name = "list_sector_assets"
    description = (
        "Return available WebP product images from the Cloud assets library, "
        "organized by sector. Use when generating product catalogs to match "
        "products with existing images. NEVER generate new images."
    )
    parameters = {
        "type": "object",
        "properties": {
            "sector": {
                "type": ["string", "null"],
                "description": "Sector code filter (e.g., 'hospitality'). Null = all sectors.",
            },
        },
        "required": ["sector"],
        "additionalProperties": False,
    }

    async def execute(self, args: dict, request: Any) -> dict:
        sector = args.get("sector")
        params = {"sector": sector} if sector else None
        data = await _cloud_get("/api/v1/catalog/assets/", params)
        if data is None:
            return {"error": "Cloud unavailable", "assets": []}
        assets = data.get("assets", []) if isinstance(data, dict) else []
        return {
            "count": len(assets),
            "assets": [
                {
                    "s3_key": a.get("s3_key"),
                    "filename": a.get("filename"),
                    "name": a.get("name"),
                    "sector": a.get("sector"),
                }
                for a in assets
            ],
        }
