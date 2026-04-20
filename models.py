"""
AI Assistant database models.

AssistantConversation — tracks conversation state per user.
AssistantActionLog — audit trail for all assistant-executed actions.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.shared.models import HubModel as HubBaseModel


class AssistantConversation(HubBaseModel):
    __tablename__ = "assistant_conversation"
    __table_args__ = (
        Index("ix_assistant_conv_hub_user", "hub_id", "created_by"),
    )

    openai_response_id: Mapped[str] = mapped_column(
        String(255), default="", server_default="",
    )
    context: Mapped[str] = mapped_column(
        String(50), default="general", server_default="general",
    )

    # Relationships
    action_logs: Mapped[list[AssistantActionLog]] = relationship(
        "AssistantActionLog", back_populates="conversation",
    )

    def __repr__(self) -> str:
        return f"<AssistantConversation id={self.id} context={self.context}>"


class AssistantActionLog(HubBaseModel):
    __tablename__ = "assistant_action_log"
    __table_args__ = (
        Index("ix_assistant_log_hub_user", "hub_id", "created_by"),
        Index("ix_assistant_log_tool", "hub_id", "tool_name"),
    )

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant_conversation.id", ondelete="SET NULL"),
        nullable=True,
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_args: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    result: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    success: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    error_message: Mapped[str] = mapped_column(Text, default="", server_default="")

    # Relationships
    conversation: Mapped[AssistantConversation | None] = relationship(
        "AssistantConversation", back_populates="action_logs",
    )

    def __repr__(self) -> str:
        status = "confirmed" if self.confirmed else "pending"
        return f"<AssistantActionLog tool={self.tool_name} {status}>"
