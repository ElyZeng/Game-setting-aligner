"""Tests for the wiki_api module."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wiki_api.pcgamingwiki import PCGamingWikiClient, _expand_path_tokens


class TestExpandPathTokens:
    def test_expand_userprofile(self):
        result = _expand_path_tokens("%USERPROFILE%/Documents/MyGame")
        assert "%" not in result
        assert "Documents/MyGame" in result

    def test_expand_home(self):
        result = _expand_path_tokens("$HOME/.config/mygame")
        assert "$HOME" not in result
        assert ".config/mygame" in result

    def test_no_tokens(self):
        path = "/absolute/path/with/no/tokens"
        assert _expand_path_tokens(path) == path


class TestPCGamingWikiClient:
    def test_instantiation(self):
        client = PCGamingWikiClient()
        assert client.timeout == 10

    def test_get_config_paths_returns_list(self, monkeypatch):
        """Should return an empty list when network is unavailable."""
        client = PCGamingWikiClient()

        # Simulate network failure
        def _fail(*args, **kwargs):
            raise ConnectionError("No network")

        if client._session:
            monkeypatch.setattr(client._session, "get", _fail)

        result = client.get_config_paths("Nonexistent Game XYZ")
        assert isinstance(result, list)


class TestPCGamingWikiClientGetConfigInfo:
    def test_get_config_info_returns_dict(self, monkeypatch):
        """get_config_info should return a dict with expected keys."""
        client = PCGamingWikiClient()

        def _fail(*args, **kwargs):
            raise ConnectionError("No network")

        if client._session:
            monkeypatch.setattr(client._session, "get", _fail)

        result = client.get_config_info("Test Game")
        assert isinstance(result, dict)
        assert "page_title" in result
        assert "url" in result
        assert "raw_paths" in result
        assert "expanded_paths" in result
        assert "error" in result

    def test_get_config_info_structure_on_network_failure(self, monkeypatch):
        """get_config_info should return a dict with error set on network failure."""
        client = PCGamingWikiClient()

        def _fail(*args, **kwargs):
            raise ConnectionError("No network")

        if client._session:
            monkeypatch.setattr(client._session, "get", _fail)

        result = client.get_config_info("Apex Legends")
        assert isinstance(result, dict)
        assert "raw_paths" in result
        assert "expanded_paths" in result
        assert isinstance(result["raw_paths"], list)
        assert isinstance(result["expanded_paths"], list)

    def test_get_config_info_has_url_field(self):
        """get_config_info should always populate 'url' with the wiki page URL."""
        client = PCGamingWikiClient()

        # Patch session.get to return empty cargo result without raising
        import json as _json
        from unittest.mock import MagicMock

        fake_response = MagicMock()
        fake_response.raise_for_status.return_value = None
        fake_response.json.return_value = {"cargoquery": []}

        if client._session:
            client._session.get = MagicMock(return_value=fake_response)

        result = client.get_config_info("Apex Legends")
        assert "url" in result
        assert "Apex" in result["url"]

    def test_get_config_info_no_session(self, monkeypatch):
        """get_config_info should handle missing requests gracefully."""
        client = PCGamingWikiClient()
        monkeypatch.setattr(client, "_session", None)

        result = client.get_config_info("Some Game")
        assert result["error"] is not None
        assert result["raw_paths"] == []
        assert result["expanded_paths"] == []
