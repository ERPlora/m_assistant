"""Tests for system prompt builder."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ..prompts import (
    build_system_prompt,
    _base_instructions,
    _user_context,
    _store_context,
    _modules_context,
    _setup_context,
    _safety_rules,
)


class TestBaseInstructions:
    def test_english(self):
        prompt = _base_instructions("en")
        assert "English" in prompt
        assert "ERPlora" in prompt

    def test_spanish(self):
        prompt = _base_instructions("es")
        assert "Spanish" in prompt

    def test_unknown_language_defaults_english(self):
        prompt = _base_instructions("xx")
        assert "English" in prompt


class TestUserContext:
    def test_user_context(self):
        prompt = _user_context("Admin User", "admin")
        assert "Admin User" in prompt
        assert "admin" in prompt


class TestStoreContext:
    def test_with_config(self):
        store = MagicMock(
            business_name="My Shop",
            tax_rate=21,
            tax_included=True,
            vat_number="ES12345678A",
        )
        hub = MagicMock(currency="EUR", language="es", country_code="ES")
        prompt = _store_context(store, hub)
        assert "My Shop" in prompt
        assert "EUR" in prompt
        assert "ES12345678A" in prompt

    def test_no_config(self):
        prompt = _store_context(None, None)
        assert "Not configured" in prompt


class TestModulesContext:
    def test_with_modules(self):
        prompt = _modules_context(["Customers", "Inventory", "POS"])
        assert "3 installed" in prompt
        assert "Customers" in prompt

    def test_no_modules(self):
        prompt = _modules_context([])
        assert "No modules" in prompt


class TestSetupContext:
    def test_all_pending(self):
        hub = MagicMock(language="", country_code="", selected_business_types=[])
        store = MagicMock(business_name="", vat_number="", is_configured=False)
        prompt = _setup_context(hub, store)
        assert "PENDING" in prompt
        assert "Setup Wizard" in prompt

    def test_regional_complete(self):
        hub = MagicMock(language="es", country_code="ES", selected_business_types=[])
        store = MagicMock(business_name="", vat_number="", is_configured=False)
        prompt = _setup_context(hub, store)
        assert "Step 1 (Regional): COMPLETE" in prompt

    def test_all_complete(self):
        hub = MagicMock(language="es", country_code="ES", selected_business_types=["pos_retail"])
        store = MagicMock(business_name="Mi Tienda", vat_number="ES123", is_configured=True)
        prompt = _setup_context(hub, store)
        assert "COMPLETE" in prompt


class TestSafetyRules:
    def test_safety_rules_present(self):
        rules = _safety_rules()
        assert "NEVER modify" in rules
        assert "confirmation" in rules
        assert "permissions" in rules


class TestBuildSystemPrompt:
    @pytest.mark.asyncio
    async def test_general_context(self, mock_request):
        hub_config = MagicMock(
            language="en", currency="EUR", timezone="UTC",
            country_code="ES", is_configured=True, hub_jwt="jwt_test",
            cloud_api_url="https://erplora.com",
        )
        store_config = MagicMock(
            business_name="Test Store", tax_rate=21, tax_included=True,
            vat_number="ES123", phone="", email="", website="", is_configured=True,
        )
        with patch("app.apps.configuration.models.HubConfig.get_config", new_callable=AsyncMock, return_value=hub_config), \
             patch("app.apps.configuration.models.StoreConfig.get_config", new_callable=AsyncMock, return_value=store_config):
            prompt = await build_system_prompt(mock_request, "general")
            assert "ERPlora" in prompt
            assert "Test Store" in prompt
            assert "Setup Wizard" not in prompt

    @pytest.mark.asyncio
    async def test_setup_context(self, mock_request):
        hub_config = MagicMock(
            language="", currency="EUR", timezone="UTC",
            country_code="", is_configured=False, hub_jwt="jwt_test",
            cloud_api_url="https://erplora.com",
            selected_business_types=[],
        )
        store_config = MagicMock(
            business_name="", tax_rate=0, tax_included=False,
            vat_number="", phone="", email="", website="", is_configured=False,
        )
        with patch("app.apps.configuration.models.HubConfig.get_config", new_callable=AsyncMock, return_value=hub_config), \
             patch("app.apps.configuration.models.StoreConfig.get_config", new_callable=AsyncMock, return_value=store_config):
            prompt = await build_system_prompt(mock_request, "setup")
            assert "Setup Wizard" in prompt
            assert "PENDING" in prompt
