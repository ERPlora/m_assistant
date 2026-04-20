"""Alembic migration environment for assistant."""
# ruff: noqa: E402
import sys
from pathlib import Path

# Ensure project root is in sys.path so app/module imports work
# env.py lives at apps/assistant/migrations/env.py → parents[3] = project root
_HUB_ROOT = Path(__file__).resolve().parents[3]
for p in (_HUB_ROOT, _HUB_ROOT / "modules"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from alembic import context
from sqlalchemy import create_engine, pool

# Import Base so Alembic sees the models
from hotframe.models.base import Base  # noqa: F401

# Import this module's models with the SAME dotted name the runtime
# uses (`assistant.models`). Never fall back to `modules.assistant.models`
# -- that would create a duplicate registration on Base.metadata.
import importlib
importlib.import_module("assistant.models")

target_metadata = Base.metadata
config = context.config
_MODULE_VERSION_TABLE = config.attributes.get("version_table") or "alembic_assistant"


def run_migrations_offline():
    url = _to_sync_url(config.get_main_option("sqlalchemy.url"))
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        render_as_batch=True,
    
        version_table=_MODULE_VERSION_TABLE,

    )
    with context.begin_transaction():
        context.run_migrations()


def _to_sync_url(url):
    """Convert async DB URL to sync for Alembic."""
    return url.replace("+asyncpg", "").replace("+aiosqlite", "")


def run_migrations_online():
    # Check if a connection was passed (from ModuleMigrationRunner)
    connectable = config.attributes.get("connection")
    if connectable is None:
        url = _to_sync_url(config.get_main_option("sqlalchemy.url"))
        connectable = create_engine(url, poolclass=pool.NullPool)

    if hasattr(connectable, "connect"):
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                render_as_batch=True,
            
                version_table=_MODULE_VERSION_TABLE,

            )
            with context.begin_transaction():
                context.run_migrations()
    else:
        context.configure(
            connection=connectable,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
        
            version_table=_MODULE_VERSION_TABLE,

        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
