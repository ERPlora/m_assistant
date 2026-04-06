"""Alembic environment for the assistant module."""

from alembic import context

target_metadata = None


def run_migrations_offline() -> None:
    context.configure(url="", target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
