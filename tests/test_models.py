"""Tests for assistant models — schema and repr validation."""


from ..models import AssistantActionLog, AssistantConversation
from .conftest import _make_conversation, _make_action_log


class TestAssistantConversation:
    def test_tablename(self):
        assert AssistantConversation.__tablename__ == "assistant_conversation"

    def test_create_conversation(self, hub_id, user_id):
        conv = _make_conversation(hub_id, user_id)
        assert conv.context == "general"
        assert conv.openai_response_id == ""

    def test_conversation_setup_context(self, hub_id, user_id):
        conv = _make_conversation(hub_id, user_id, context="setup")
        assert conv.context == "setup"

    def test_conversation_with_response_id(self, conversation_with_response):
        assert conversation_with_response.openai_response_id == "resp_abc123"

    def test_conversation_fields_exist(self):
        """Verify all expected columns are mapped."""
        cols = {c.name for c in AssistantConversation.__table__.columns}
        assert "openai_response_id" in cols
        assert "context" in cols
        assert "hub_id" in cols
        assert "created_by" in cols


class TestAssistantActionLog:
    def test_tablename(self):
        assert AssistantActionLog.__tablename__ == "assistant_action_log"

    def test_create_action_log(self, hub_id, user_id, conversation):
        log = _make_action_log(
            hub_id, user_id, conversation,
            tool_name="get_hub_config", tool_args={},
            result={"language": "es"}, success=True, confirmed=True,
        )
        assert log.tool_name == "get_hub_config"
        assert log.success is True

    def test_pending_action(self, pending_action):
        assert pending_action.confirmed is False
        assert pending_action.success is False

    def test_confirmed_action(self, confirmed_action):
        assert confirmed_action.confirmed is True
        assert confirmed_action.success is True

    def test_action_log_with_error(self, hub_id, user_id, conversation):
        log = _make_action_log(
            hub_id, user_id, conversation,
            tool_name="create_product", tool_args={"name": "Test"},
            result={"error": "Product already exists"}, success=False,
            confirmed=True, error_message="Product already exists",
        )
        assert log.success is False
        assert "already exists" in log.error_message

    def test_action_log_fields_exist(self):
        cols = {c.name for c in AssistantActionLog.__table__.columns}
        assert "tool_name" in cols
        assert "tool_args" in cols
        assert "result" in cols
        assert "success" in cols
        assert "confirmed" in cols
        assert "error_message" in cols
        assert "conversation_id" in cols
