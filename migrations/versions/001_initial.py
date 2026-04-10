"""Initial assistant tables.

Revision ID: 001
Create Date: 2026-04-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    """Check if a table already exists (handles core migrations that pre-create tables)."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :name)"),
        {"name": name},
    )
    return result.scalar()


def upgrade() -> None:
    if not _table_exists("assistant_conversation"):
        op.create_table(
            "assistant_conversation",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("hub_id", sa.Uuid(), nullable=False, index=True),
            sa.Column("openai_response_id", sa.String(255), server_default="", nullable=False),
            sa.Column("context", sa.String(50), server_default="general", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_assistant_conv_hub_user", "assistant_conversation", ["hub_id", "created_by"])

    if not _table_exists("assistant_action_log"):
        op.create_table(
            "assistant_action_log",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("hub_id", sa.Uuid(), nullable=False, index=True),
            sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("assistant_conversation.id", ondelete="SET NULL"), nullable=True),
            sa.Column("tool_name", sa.String(100), nullable=False),
            sa.Column("tool_args", postgresql.JSONB(), server_default="{}", nullable=False),
            sa.Column("result", postgresql.JSONB(), server_default="{}", nullable=False),
            sa.Column("success", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("confirmed", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("error_message", sa.Text(), server_default="", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_assistant_log_hub_user", "assistant_action_log", ["hub_id", "created_by"])
        op.create_index("ix_assistant_log_tool", "assistant_action_log", ["hub_id", "tool_name"])


def downgrade() -> None:
    op.drop_table("assistant_action_log")
    op.drop_table("assistant_conversation")
