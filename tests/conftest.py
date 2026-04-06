"""Fixtures for assistant module tests."""

from __future__ import annotations

import uuid
from datetime import datetime, UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def hub_id():
    return uuid.uuid4()


@pytest.fixture
def user_id():
    return uuid.uuid4()


def _make_conversation(hub_id, user_id, *, context="general", response_id=""):
    """Create a lightweight conversation object (no ORM instrumentation)."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        hub_id=hub_id,
        created_by=user_id,
        context=context,
        openai_response_id=response_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        is_deleted=False,
        deleted_at=None,
        updated_by=None,
        action_logs=[],
    )


def _make_action_log(hub_id, user_id, conversation, *, tool_name="create_employee",
                     tool_args=None, result=None, success=False, confirmed=False,
                     error_message=""):
    return SimpleNamespace(
        id=uuid.uuid4(),
        hub_id=hub_id,
        created_by=user_id,
        conversation_id=conversation.id,
        conversation=conversation,
        tool_name=tool_name,
        tool_args=tool_args or {"name": "Juan", "email": "juan@test.com", "pin": "1234", "role_name": "employee"},
        result=result or {},
        success=success,
        confirmed=confirmed,
        error_message=error_message,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        is_deleted=False,
        deleted_at=None,
        updated_by=None,
    )


@pytest.fixture
def conversation(hub_id, user_id):
    return _make_conversation(hub_id, user_id)


@pytest.fixture
def conversation_with_response(hub_id, user_id):
    return _make_conversation(hub_id, user_id, response_id="resp_abc123")


@pytest.fixture
def pending_action(hub_id, user_id, conversation):
    return _make_action_log(hub_id, user_id, conversation)


@pytest.fixture
def confirmed_action(hub_id, user_id, conversation):
    return _make_action_log(
        hub_id, user_id, conversation,
        success=True, confirmed=True,
        result={"success": True, "employee_id": str(uuid.uuid4()), "name": "Juan"},
    )


@pytest.fixture
def mock_request(hub_id, user_id):
    """A mock FastAPI request with state."""
    request = MagicMock()
    request.state.db = AsyncMock()
    request.state.hub_id = hub_id
    request.state.user_id = user_id
    request.state.user_name = "Admin"
    request.state.user_role = "admin"
    request.state.user_permissions = [
        "assistant.use_chat",
        "assistant.use_setup_mode",
        "assistant.view_logs",
        "assistant.manage_settings",
    ]
    request.app.state.module_registry = MagicMock()
    request.app.state.module_registry.get_menu_items.return_value = [
        {"module_id": "customers", "label": "Customers", "icon": "people-outline"},
        {"module_id": "inventory", "label": "Inventory", "icon": "cube-outline"},
    ]
    request.app.state.templates = MagicMock()
    return request
