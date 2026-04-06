"""
Compatibility helpers for assistant setup state.

HubConfig uses `selected_business_types` for setup selection.
These helpers provide a clean interface.
"""

from __future__ import annotations


def get_selected_blocks(config: object) -> list[str]:
    """Return the selected business blocks/types."""
    blocks = getattr(config, "selected_business_types", None)
    if blocks:
        return [slug for slug in blocks if slug]
    return []


def get_primary_selected_block(config: object) -> str:
    """Return the primary selected block slug, if any."""
    solution_slug = getattr(config, "solution_slug", "") or ""
    if solution_slug:
        return solution_slug
    selected = get_selected_blocks(config)
    return selected[0] if selected else ""


def set_selected_blocks(config: object, block_slugs: list[str]) -> list[str]:
    """Persist selected blocks on the config object."""
    normalized = [slug for slug in block_slugs if slug]
    config.selected_business_types = normalized
    return normalized
