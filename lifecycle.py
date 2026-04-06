from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def on_install(session: AsyncSession, hub_id: UUID) -> None:
    pass


async def on_activate(session: AsyncSession, hub_id: UUID) -> None:
    pass


async def on_deactivate(session: AsyncSession, hub_id: UUID) -> None:
    pass


async def on_uninstall(session: AsyncSession, hub_id: UUID) -> None:
    pass


async def on_upgrade(
    session: AsyncSession, hub_id: UUID, from_version: str, to_version: str,
) -> None:
    pass
