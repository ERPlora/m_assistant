"""Tests for assistant routes — helpers and format functions."""


from ..routes import _format_confirmation_text


class TestFormatConfirmationText:
    def test_update_store_config(self):
        text = _format_confirmation_text("update_store_config", {
            "business_name": "Mi Tienda",
            "phone": None,
            "email": "test@test.com",
        })
        assert "Update store" in text
        assert "business_name" in text

    def test_create_employee(self):
        text = _format_confirmation_text("create_employee", {
            "name": "Juan",
            "role_name": "manager",
        })
        assert "Juan" in text
        assert "manager" in text

    def test_select_blocks(self):
        text = _format_confirmation_text("select_blocks", {
            "block_slugs": ["pos_retail", "crm"],
        })
        assert "pos_retail" in text

    def test_unknown_tool(self):
        text = _format_confirmation_text("unknown_tool", {"foo": "bar"})
        assert "unknown_tool" in text
        assert "foo=bar" in text

    def test_create_product(self):
        text = _format_confirmation_text("create_product", {"name": "Widget"})
        assert "Widget" in text

    def test_complete_setup(self):
        text = _format_confirmation_text("complete_setup_step", {})
        assert "Complete hub setup" in text

    def test_create_tax_class(self):
        text = _format_confirmation_text("create_tax_class", {"name": "IVA", "rate": 21})
        assert "IVA" in text
        assert "21" in text

    def test_set_regional_config(self):
        text = _format_confirmation_text("set_regional_config", {
            "language": "es",
            "country_code": "ES",
            "timezone": None,
        })
        assert "Set region" in text
        assert "language=es" in text


class TestSchemas:
    def test_chat_request_validation(self):
        from ..schemas import ChatRequest
        req = ChatRequest(message="Hello")
        assert req.message == "Hello"
        assert req.context == "general"

    def test_chat_request_empty_message(self):
        from ..schemas import ChatRequest
        import pytest
        with pytest.raises(Exception):
            ChatRequest(message="")

    def test_chat_request_setup_context(self):
        from ..schemas import ChatRequest
        req = ChatRequest(message="Hi", context="setup")
        assert req.context == "setup"

    def test_chat_response(self):
        from ..schemas import ChatResponse
        resp = ChatResponse(request_id="abc123", conversation_id="conv456")
        assert resp.request_id == "abc123"

    def test_skip_setup_response(self):
        from ..schemas import SkipSetupResponse
        resp = SkipSetupResponse(success=True)
        assert resp.redirect_url == "/"


class TestStreamCache:
    def test_cache_set_and_get(self):
        from ..routes import _stream_cache
        _stream_cache["test_key"] = {"message": "hello"}
        assert _stream_cache.get("test_key") == {"message": "hello"}
        # Cleanup
        _stream_cache.pop("test_key", None)

    def test_cache_pop(self):
        from ..routes import _stream_cache
        _stream_cache["test_pop"] = {"message": "world"}
        val = _stream_cache.pop("test_pop", None)
        assert val == {"message": "world"}
        assert _stream_cache.get("test_pop") is None
