"""
AI context provider for the assistant module.

Returns contextual information about the assistant module itself — current
conversation state, usage stats, and configuration — so the AI can reference
its own status when needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import Request


async def get_ai_context(request: Request) -> dict[str, Any]:
    """Return context about the assistant module for the AI system prompt."""
    from app.core.db.query import HubQuery

    from .models import AssistantActionLog, AssistantConversation

    db = request.state.db
    hub_id = request.state.hub_id
    user_id = getattr(request.state, "user_id", None)

    # Count conversations
    conv_query = HubQuery(AssistantConversation, db, hub_id)
    if user_id:
        conv_query = conv_query.filter(
            AssistantConversation.created_by == user_id,
        )
    conversations = await conv_query.all()
    total_conversations = len(conversations)

    # Count action logs
    log_query = HubQuery(AssistantActionLog, db, hub_id)
    if user_id:
        log_query = log_query.filter(
            AssistantActionLog.created_by == user_id,
        )
    logs = await log_query.all()
    total_actions = len(logs)
    successful_actions = sum(1 for log in logs if log.success)

    return {
        "module": "assistant",
        "total_conversations": total_conversations,
        "total_actions": total_actions,
        "successful_actions": successful_actions,
    }
