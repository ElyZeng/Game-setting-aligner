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
