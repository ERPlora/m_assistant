"""
Product catalog draft generator.

Returns a starter product catalog (name, price, tax_rate, image_s3_key) for
a given set of business types, matching each product to an existing WebP
image in the Cloud assets library when possible. Never generates images.

The tool RETURNS the draft — it does NOT write products to DB. Writing is
handled by module services (e.g., sales.ProductService) via the generic
execute tool when a sales/pos/inventory module is active.
"""
from __future__ import annotations

import logging
from typing import Any

from apps.ai.registry import AssistantTool, register_tool

logger = logging.getLogger(__name__)


# Typical products per business type (starter templates the assistant refines).
# Key is BusinessType.code; value is a list of typical product names with
# suggested price ranges and tax rate hints (country-neutral; Spain defaults).
TYPICAL_PRODUCTS: dict[str, list[dict]] = {
    "bar": [
        {"name": "Cerveza", "price": 2.50, "image_hint": "beer"},
        {"name": "Café solo", "price": 1.20, "image_hint": "coffee_espresso"},
        {"name": "Café con leche", "price": 1.50, "image_hint": "coffee_latte"},
        {"name": "Coca-Cola", "price": 2.00, "image_hint": "soda"},
        {"name": "Agua mineral", "price": 1.50, "image_hint": "water"},
        {"name": "Tapa de tortilla", "price": 3.00, "image_hint": "tortilla"},
        {"name": "Bocadillo de jamón", "price": 4.50, "image_hint": "sandwich_ham"},
    ],
    "cafeteria": [
        {"name": "Café solo", "price": 1.20, "image_hint": "coffee_espresso"},
        {"name": "Café cortado", "price": 1.30, "image_hint": "coffee_cortado"},
        {"name": "Café con leche", "price": 1.50, "image_hint": "coffee_latte"},
        {"name": "Té", "price": 1.50, "image_hint": "tea"},
        {"name": "Croissant", "price": 1.80, "image_hint": "croissant"},
        {"name": "Muffin", "price": 2.20, "image_hint": "muffin"},
        {"name": "Sandwich mixto", "price": 3.50, "image_hint": "sandwich"},
    ],
    "restaurant": [
        {"name": "Menú del día", "price": 12.00, "image_hint": "menu"},
        {"name": "Ensalada mixta", "price": 8.00, "image_hint": "salad"},
        {"name": "Paella", "price": 14.00, "image_hint": "paella"},
        {"name": "Filete con patatas", "price": 15.00, "image_hint": "steak"},
        {"name": "Pescado del día", "price": 18.00, "image_hint": "fish"},
        {"name": "Flan casero", "price": 4.50, "image_hint": "flan"},
        {"name": "Vino tinto (copa)", "price": 3.00, "image_hint": "wine_red"},
    ],
    "hair_salon": [
        {"name": "Corte de pelo (mujer)", "price": 25.00, "image_hint": "hair_cut_female"},
        {"name": "Corte de pelo (hombre)", "price": 15.00, "image_hint": "hair_cut_male"},
        {"name": "Tinte", "price": 45.00, "image_hint": "hair_color"},
        {"name": "Mechas", "price": 60.00, "image_hint": "hair_highlights"},
        {"name": "Peinado", "price": 20.00, "image_hint": "hair_style"},
    ],
    "beauty_center": [
        {"name": "Manicura", "price": 18.00, "image_hint": "manicure"},
        {"name": "Pedicura", "price": 22.00, "image_hint": "pedicure"},
        {"name": "Depilación cera", "price": 15.00, "image_hint": "waxing"},
        {"name": "Masaje relajante (45 min)", "price": 35.00, "image_hint": "massage"},
    ],
    # Add a generic fallback for types not listed
    "_default": [
        {"name": "Producto 1", "price": 10.00, "image_hint": None},
        {"name": "Producto 2", "price": 15.00, "image_hint": None},
        {"name": "Servicio básico", "price": 25.00, "image_hint": None},
    ],
}


async def _fetch_assets_for_sectors(sectors: list[str]) -> list[dict]:
    """Fetch the union of assets across the requested sectors."""
    from apps.shared.services.cloud_client import _client_instance
    if not _client_instance:
        return []
    merged: dict[str, dict] = {}
    for sector in sectors:
        try:
            resp = await _client_instance.get(
                "/api/v1/catalog/assets/", params={"sector": sector}
            )
        except Exception as e:
            logger.warning("Cloud GET assets failed for sector=%s: %s", sector, e)
            continue
        if not resp or not isinstance(resp, dict):
            continue
        for a in resp.get("assets", []) or []:
            key = a.get("s3_key")
            if key and key not in merged:
                merged[key] = a
    return list(merged.values())


async def _lookup_business_type_sectors(business_types: list[str]) -> list[str]:
    """Resolve business_type codes to their sector codes via Cloud catalog."""
    from apps.shared.services.cloud_client import _client_instance
    if not _client_instance or not business_types:
        return []
    sectors: set[str] = set()
    for bt in business_types:
        try:
            resp = await _client_instance.get(f"/api/v1/catalog/business-types/{bt}/")
        except Exception as e:
            logger.warning("Cloud GET business-type/%s failed: %s", bt, e)
            continue
        if isinstance(resp, dict):
            sector_code = resp.get("sector_code")
            if sector_code:
                sectors.add(sector_code)
    return list(sectors)


def _match_image(hint: str | None, assets: list[dict]) -> str | None:
    """Find best-match S3 key for a product name hint. Return None if no match."""
    if not hint:
        return None
    hint_lower = hint.lower()
    # Exact filename stem match first
    for a in assets:
        stem = (a.get("filename", "") or "").rsplit(".", 1)[0].lower()
        if stem == hint_lower:
            return a.get("s3_key")
    # Partial name match (stem contains hint or vice versa)
    for a in assets:
        stem = (a.get("filename", "") or "").rsplit(".", 1)[0].lower()
        if hint_lower in stem or stem in hint_lower:
            return a.get("s3_key")
    # Name field match (the `name` is filename with underscores replaced by spaces)
    for a in assets:
        name = (a.get("name", "") or "").lower()
        if hint_lower in name:
            return a.get("s3_key")
    return None


@register_tool
class DraftProductsForBusiness(AssistantTool):
    name = "draft_products_for_business"
    description = (
        "Generate a starter product catalog (name, price, tax_rate, image_s3_key) "
        "for the given business types. The tool matches each product to an "
        "existing WebP image in the Cloud assets library when possible. "
        "Returns a draft — does NOT write to the database. The assistant can "
        "then show it to the user for review and trigger a write via the "
        "module services (e.g., sales.ProductService) using the generic "
        "execute tool. NEVER generate images."
    )
    parameters = {
        "type": "object",
        "properties": {
            "business_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of BusinessType codes, e.g. ['bar', 'cafeteria']",
            },
            "country": {
                "type": ["string", "null"],
                "description": "ISO-2 country code for tax defaults (e.g., 'ES'). Null = use hub default.",
            },
            "max_products": {
                "type": ["integer", "null"],
                "description": "Maximum products to return (default 20)",
            },
        },
        "required": ["business_types", "country", "max_products"],
        "additionalProperties": False,
    }

    async def execute(self, args: dict, request: Any) -> dict:
        business_types = args.get("business_types") or []
        country = (args.get("country") or "").upper() or None
        max_products = args.get("max_products") or 20

        if not business_types:
            return {"error": "At least one business_type is required", "products": []}

        # Country-based default tax rate (GPT knows more nuance; this is a hint)
        default_tax = {
            "ES": 21.0, "PT": 23.0, "FR": 20.0, "IT": 22.0, "DE": 19.0,
            "MX": 16.0, "AR": 21.0, "CO": 19.0, "CL": 19.0,
        }.get(country or "", 21.0)

        # Resolve sectors to fetch relevant asset library
        sectors = await _lookup_business_type_sectors(business_types)
        assets = await _fetch_assets_for_sectors(sectors) if sectors else []

        # Compose draft products
        products: list[dict] = []
        for bt in business_types:
            templates = TYPICAL_PRODUCTS.get(bt, TYPICAL_PRODUCTS["_default"])
            for t in templates:
                if len(products) >= max_products:
                    break
                s3_key = _match_image(t.get("image_hint"), assets)
                products.append({
                    "name": t["name"],
                    "price": t["price"],
                    "tax_rate": default_tax,
                    "image_s3_key": s3_key,
                    "business_type": bt,
                })
            if len(products) >= max_products:
                break

        return {
            "count": len(products),
            "sectors_used": sectors,
            "assets_available": len(assets),
            "products": products,
            "notes": (
                "This is a draft. The assistant should present it to the user "
                "for review, adjust quantities/prices as requested, and then "
                "write products via module services (e.g., sales.ProductService) "
                "using the generic execute tool. Do not generate images — "
                "use only image_s3_key values returned here."
            ),
        }
