"""Tests for tool registry integration."""

from apps.ai.registry import (
    AssistantTool,
    TOOL_REGISTRY,
    register_tool,
    get_tools_for_user,
    tools_to_openai_schema,
    unregister_module_tools,
)


class TestToolRegistry:
    def test_hub_tools_registered(self):
        """Hub core tools should be importable and registrable."""
        # Import triggers registration
        from ..tools import hub_tools  # noqa: F401
        from ..tools import setup_tools  # noqa: F401

        # At minimum these should exist
        assert "get_hub_config" in TOOL_REGISTRY
        assert "get_store_config" in TOOL_REGISTRY
        assert "list_modules" in TOOL_REGISTRY
        assert "list_roles" in TOOL_REGISTRY
        assert "list_employees" in TOOL_REGISTRY
        assert "update_store_config" in TOOL_REGISTRY

        # install_module, enable_module, disable_module removed — now in _modules service
        assert "install_module" not in TOOL_REGISTRY
        assert "enable_module" not in TOOL_REGISTRY
        assert "disable_module" not in TOOL_REGISTRY

    def test_setup_tools_registered(self):
        from ..tools import setup_tools  # noqa: F401
        assert "set_regional_config" in TOOL_REGISTRY
        assert "set_business_info" in TOOL_REGISTRY
        assert "set_tax_config" in TOOL_REGISTRY
        assert "complete_setup_step" in TOOL_REGISTRY

    def test_get_tools_for_user_general(self):
        from ..tools import hub_tools, setup_tools  # noqa: F401
        tools = get_tools_for_user(["assistant.use_chat"], setup_mode=False)
        tool_names = [t.name for t in tools]
        # General context should include read tools
        assert "get_hub_config" in tool_names
        # Should NOT include setup-only tools
        assert "set_regional_config" not in tool_names

    def test_get_tools_for_user_setup(self):
        from ..tools import hub_tools, setup_tools  # noqa: F401
        tools = get_tools_for_user(
            ["assistant.use_chat", "assistant.use_setup_mode"],
            setup_mode=True,
        )
        tool_names = [t.name for t in tools]
        # Setup context should include setup tools
        assert "set_regional_config" in tool_names

    def test_tools_to_openai_schema(self):
        from ..tools import hub_tools  # noqa: F401
        tool = TOOL_REGISTRY["get_hub_config"]
        schema = tools_to_openai_schema([tool])
        assert len(schema) == 1
        assert schema[0]["type"] == "function"
        assert schema[0]["function"]["name"] == "get_hub_config"

    def test_confirmation_flag(self):
        from ..tools import hub_tools  # noqa: F401
        # requires_confirmation removed from all tools — system prompt controls this
        assert TOOL_REGISTRY["get_hub_config"].requires_confirmation is False
        assert TOOL_REGISTRY["update_store_config"].requires_confirmation is False

    def test_permission_requirements(self):
        from ..tools import hub_tools  # noqa: F401
        assert TOOL_REGISTRY["update_store_config"].required_permission == "assistant.use_chat"
        assert TOOL_REGISTRY["create_role"].required_permission == "assistant.use_setup_mode"

    def test_setup_only_flag(self):
        from ..tools import setup_tools  # noqa: F401
        assert TOOL_REGISTRY["set_regional_config"].setup_only is True
        assert TOOL_REGISTRY["get_hub_config"].setup_only is False


class TestToolBase:
    def test_tool_subclass(self):
        class MyTool(AssistantTool):
            name = "test_tool"
            description = "A test tool"
            parameters = {"type": "object", "properties": {}}

        tool = MyTool()
        assert tool.name == "test_tool"
        assert tool.requires_confirmation is False
        assert tool.setup_only is False

    def test_unregister_module_tools(self):
        @register_tool
        class TempTool(AssistantTool):
            name = "_temp_test_tool"
            description = "Temporary"
            module_id = "_test_module"
            parameters = {}

        assert "_temp_test_tool" in TOOL_REGISTRY
        removed = unregister_module_tools("_test_module")
        assert removed == 1
        assert "_temp_test_tool" not in TOOL_REGISTRY
