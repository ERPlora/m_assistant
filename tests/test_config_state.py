"""Tests for config_state helpers."""

from unittest.mock import MagicMock

from ..config_state import get_selected_blocks, get_primary_selected_block, set_selected_blocks


class TestGetSelectedBlocks:
    def test_from_selected_business_types(self):
        config = MagicMock(selected_business_types=["pos_retail", "crm"])
        assert get_selected_blocks(config) == ["pos_retail", "crm"]

    def test_empty_returns_empty(self):
        config = MagicMock(selected_business_types=[])
        assert get_selected_blocks(config) == []

    def test_filters_empty_strings(self):
        config = MagicMock(selected_business_types=["pos_retail", "", "crm"])
        assert get_selected_blocks(config) == ["pos_retail", "crm"]

    def test_no_attribute_returns_empty(self):
        config = MagicMock(spec=[])
        assert get_selected_blocks(config) == []


class TestGetPrimarySelectedBlock:
    def test_from_solution_slug(self):
        config = MagicMock(solution_slug="pos_retail", selected_business_types=["pos_retail", "crm"])
        assert get_primary_selected_block(config) == "pos_retail"

    def test_from_first_block(self):
        config = MagicMock(solution_slug="", selected_business_types=["crm", "pos_retail"])
        assert get_primary_selected_block(config) == "crm"

    def test_empty(self):
        config = MagicMock(solution_slug="", selected_business_types=[])
        assert get_primary_selected_block(config) == ""


class TestSetSelectedBlocks:
    def test_set_blocks(self):
        config = MagicMock()
        result = set_selected_blocks(config, ["pos_retail", "crm"])
        assert result == ["pos_retail", "crm"]
        assert config.selected_business_types == ["pos_retail", "crm"]

    def test_filters_empty(self):
        config = MagicMock()
        result = set_selected_blocks(config, ["pos_retail", "", "crm"])
        assert result == ["pos_retail", "crm"]
