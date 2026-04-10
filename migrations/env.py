"""
Alembic environment for the assistant module.

Uses per-module version table: alembic_assistant.
Migrations are hand-written (op.create_table), so no model imports needed.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No target_metadata needed — migrations use explicit op.create_table()
target_metadata = None

# Per-module version table
VERSION_TABLE = "alembic_assistant"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generate SQL)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        version_table=VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (execute against DB)."""
    connectable = context.config.attributes.get("connection", None)
    if connectable is None:
        connectable = create_engine(
            config.get_main_option("sqlalchemy.url"),
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table=VERSION_TABLE,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
