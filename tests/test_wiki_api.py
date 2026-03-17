"""Tests for the wiki_api module."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wiki_api.pcgamingwiki import (
    PCGamingWikiClient,
    _expand_path_tokens,
    _is_registry_path,
    _parse_gamedata_config,
    _find_template_blocks,
    _split_by_pipe,
)


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


# ---------------------------------------------------------------------------
# Apex Legends wikitext snippet used across multiple tests
# ---------------------------------------------------------------------------

_APEX_WIKITEXT = (
    "{{Game data|\n"
    "{{Game data/config|Windows|"
    "{{P|userprofile}}\\Saved Games\\Respawn\\Apex\\local\\settings.cfg|"
    "{{P|userprofile}}\\Saved Games\\Respawn\\Apex\\local\\videoconfig.txt|"
    "{{P|userprofile}}\\Saved Games\\Respawn\\Apex\\profile\\profile.cfg|"
    "{{P|hkcu}}\\SOFTWARE\\Valve\\Source\\r2}}\n"
    "}}"
)


# ---------------------------------------------------------------------------
# _is_registry_path tests
# ---------------------------------------------------------------------------

class TestIsRegistryPath:
    def test_hkcu_path_is_registry(self):
        assert _is_registry_path("{{P|hkcu}}\\SOFTWARE\\Valve\\Source\\r2") is True

    def test_hklm_path_is_registry(self):
        assert _is_registry_path("{{P|hklm}}\\SOFTWARE\\Example") is True

    def test_file_path_is_not_registry(self):
        assert _is_registry_path("{{P|userprofile}}\\Saved Games\\settings.cfg") is False

    def test_empty_string_is_not_registry(self):
        assert _is_registry_path("") is False

    def test_case_insensitive_hkcu(self):
        assert _is_registry_path("{{P|HKCU}}\\SOFTWARE\\Test") is True


# ---------------------------------------------------------------------------
# _split_by_pipe tests
# ---------------------------------------------------------------------------

class TestSplitByPipe:
    def test_simple_split(self):
        assert _split_by_pipe("a|b|c") == ["a", "b", "c"]

    def test_nested_template_not_split(self):
        result = _split_by_pipe("Game data/config|Windows|{{P|userprofile}}\\path")
        assert len(result) == 3
        assert result[2] == "{{P|userprofile}}\\path"

    def test_single_part(self):
        assert _split_by_pipe("only") == ["only"]

    def test_empty_string(self):
        assert _split_by_pipe("") == []


# ---------------------------------------------------------------------------
# _find_template_blocks tests
# ---------------------------------------------------------------------------

class TestFindTemplateBlocks:
    def test_finds_single_block(self):
        wt = "{{Game data/config|Windows|C:\\path}}"
        blocks = _find_template_blocks(wt, "Game data/config")
        assert len(blocks) == 1
        assert blocks[0] == wt

    def test_finds_nested_tokens(self):
        wt = "{{Game data/config|Windows|{{P|userprofile}}\\path}}"
        blocks = _find_template_blocks(wt, "Game data/config")
        assert len(blocks) == 1
        assert "{{P|userprofile}}" in blocks[0]

    def test_no_match_returns_empty(self):
        blocks = _find_template_blocks("No template here", "Game data/config")
        assert blocks == []

    def test_finds_multiple_blocks(self):
        wt = "{{Game data/config|Windows|C:\\a}}{{Game data/config|Linux|/home/b}}"
        blocks = _find_template_blocks(wt, "Game data/config")
        assert len(blocks) == 2


# ---------------------------------------------------------------------------
# _parse_gamedata_config tests
# ---------------------------------------------------------------------------

class TestParseGamedataConfig:
    def test_apex_legends_wikitext_yields_four_raw_paths(self):
        """Apex Legends wikitext snippet should produce 4 raw paths (3 files + 1 registry)."""
        raw, _ = _parse_gamedata_config(_APEX_WIKITEXT)
        assert len(raw) == 4

    def test_apex_legends_three_file_paths_in_expanded(self):
        """3 file paths (not registry) should appear in expanded_paths."""
        _, expanded = _parse_gamedata_config(_APEX_WIKITEXT)
        assert len(expanded) == 3

    def test_apex_legends_registry_path_not_in_expanded(self):
        """Registry path {{P|hkcu}}\\... must not appear in expanded_paths."""
        _, expanded = _parse_gamedata_config(_APEX_WIKITEXT)
        for path in expanded:
            # Only file paths under Saved Games should appear; no registry keys
            assert "hkcu" not in path.lower()

    def test_apex_legends_raw_contains_registry(self):
        """Registry path must be preserved in raw_paths for diagnostics."""
        raw, _ = _parse_gamedata_config(_APEX_WIKITEXT)
        assert any("hkcu" in r.lower() for r in raw)

    def test_apex_legends_expanded_contains_saved_games_paths(self):
        """Expanded paths should include the Saved Games sub-paths."""
        _, expanded = _parse_gamedata_config(_APEX_WIKITEXT)
        # All three file paths are under Saved Games\Respawn\Apex
        for path in expanded:
            assert "Respawn" in path or "Apex" in path

    def test_os_filter_excludes_non_windows(self):
        """Non-Windows blocks should be ignored when os_filter='Windows'."""
        wt = (
            "{{Game data/config|Linux|/home/user/.config/game.cfg}}"
            "{{Game data/config|Windows|C:\\game\\settings.cfg}}"
        )
        raw, expanded = _parse_gamedata_config(wt, os_filter="Windows")
        assert len(raw) == 1
        assert "settings.cfg" in raw[0]

    def test_empty_wikitext_returns_empty(self):
        raw, expanded = _parse_gamedata_config("")
        assert raw == []
        assert expanded == []

    def test_no_game_data_config_block(self):
        raw, expanded = _parse_gamedata_config("{{Game data/saving|Windows|C:\\save}}")
        assert raw == []
        assert expanded == []


# ---------------------------------------------------------------------------
# _expand_path_tokens – additional token tests
# ---------------------------------------------------------------------------

class TestExpandPathTokensAdditional:
    def test_expand_wiki_userprofile_token(self):
        """{{P|userprofile}} should expand and produce the Saved Games sub-path."""
        from wiki_api import pcgamingwiki as mod
        saved = mod._WIKI_TAG_MAP.get("{{P|userprofile}}")
        mod._WIKI_TAG_MAP["{{P|userprofile}}"] = "C:\\Users\\testuser"
        try:
            result = mod._expand_path_tokens("{{P|userprofile}}\\Saved Games\\Respawn\\Apex")
            assert "testuser" in result
            assert "Saved Games" in result
        finally:
            if saved is not None:
                mod._WIKI_TAG_MAP["{{P|userprofile}}"] = saved

    def test_expand_userprofile_token_contains_apex_subpath(self):
        """Expanding a {{P|userprofile}} path should contain the Apex subpath."""
        result = _expand_path_tokens("{{P|userprofile}}\\Saved Games\\Respawn\\Apex\\local\\settings.cfg")
        assert "Saved Games" in result
        assert "Respawn" in result
        assert "settings.cfg" in result

    def test_registry_path_not_meaningful_after_expand(self):
        """Expanding a registry path token should not produce a file-like path."""
        # We do NOT expand registry tokens – they remain or get normalised oddly.
        # The important thing is _is_registry_path catches them before expansion.
        path = "{{P|hkcu}}\\SOFTWARE\\Valve\\Source\\r2"
        assert _is_registry_path(path) is True


# ---------------------------------------------------------------------------
# PCGamingWikiClient._query_mediawiki_raw tests (mocked)
# ---------------------------------------------------------------------------

class TestQueryMediawikiRaw:
    """Unit tests for the MediaWiki API fallback using mocked HTTP responses."""

    _MEDIAWIKI_RESPONSE = {
        "query": {
            "pages": {
                "12345": {
                    "pageid": 12345,
                    "title": "Apex Legends",
                    "revisions": [
                        {
                            "slots": {
                                "main": {
                                    "*": _APEX_WIKITEXT
                                }
                            }
                        }
                    ],
                }
            }
        }
    }

    def _make_session_mock(self, cargo_response, mediawiki_response):
        """Return a mock session whose .get() returns different responses by call order."""
        from unittest.mock import MagicMock

        cargo_resp = MagicMock()
        cargo_resp.raise_for_status.return_value = None
        cargo_resp.json.return_value = cargo_response

        wiki_resp = MagicMock()
        wiki_resp.raise_for_status.return_value = None
        wiki_resp.json.return_value = mediawiki_response

        mock_session = MagicMock()
        mock_session.get.side_effect = [cargo_resp, wiki_resp]
        return mock_session

    def test_mediawiki_fallback_called_when_cargo_empty(self, monkeypatch):
        """When Cargo returns empty, _query_mediawiki_raw should be tried."""
        client = PCGamingWikiClient()
        called = []

        def fake_mediawiki(title):
            called.append(title)
            return (["path1"], ["expanded1"])

        monkeypatch.setattr(client, "_query_cargo_raw", lambda t: ([], []))
        monkeypatch.setattr(client, "_query_mediawiki_raw", fake_mediawiki)

        result = client.get_config_info("Apex Legends")
        assert called == ["Apex Legends"]
        assert result["raw_paths"] == ["path1"]
        assert result["expanded_paths"] == ["expanded1"]

    def test_mediawiki_not_called_when_cargo_succeeds(self, monkeypatch):
        """When Cargo returns results, the MediaWiki fallback should not be called."""
        client = PCGamingWikiClient()
        called = []

        monkeypatch.setattr(client, "_query_cargo_raw", lambda t: (["cargo_path"], ["cargo_expanded"]))
        monkeypatch.setattr(client, "_query_mediawiki_raw", lambda t: called.append(t) or ([], []))

        client.get_config_info("Some Game")
        assert called == []

    def test_query_mediawiki_raw_parses_apex_wikitext(self, monkeypatch):
        """_query_mediawiki_raw should return 4 raw + 3 expanded paths from Apex wikitext."""
        from unittest.mock import MagicMock

        client = PCGamingWikiClient()

        fake_resp = MagicMock()
        fake_resp.raise_for_status.return_value = None
        fake_resp.json.return_value = self._MEDIAWIKI_RESPONSE

        if client._session:
            monkeypatch.setattr(client._session, "get", MagicMock(return_value=fake_resp))

        raw, expanded = client._query_mediawiki_raw("Apex Legends")
        assert len(raw) == 4, f"expected 4 raw paths, got {raw}"
        assert len(expanded) == 3, f"expected 3 expanded paths, got {expanded}"
        # All expanded paths should contain the Apex sub-directory
        for path in expanded:
            assert "Respawn" in path or "Apex" in path

    def test_query_mediawiki_raw_no_session(self, monkeypatch):
        """_query_mediawiki_raw returns empty lists when session is None."""
        client = PCGamingWikiClient()
        monkeypatch.setattr(client, "_session", None)
        raw, expanded = client._query_mediawiki_raw("Apex Legends")
        assert raw == []
        assert expanded == []

    def test_query_mediawiki_raw_network_failure(self, monkeypatch):
        """_query_mediawiki_raw returns empty lists on network error."""
        from unittest.mock import MagicMock

        client = PCGamingWikiClient()
        if client._session:
            monkeypatch.setattr(client._session, "get", MagicMock(side_effect=ConnectionError("fail")))
        raw, expanded = client._query_mediawiki_raw("Apex Legends")
        assert raw == []
        assert expanded == []

    def test_get_config_info_with_mediawiki_response(self, monkeypatch):
        """get_config_info should populate raw_paths and expanded_paths via MediaWiki fallback."""
        from unittest.mock import MagicMock

        client = PCGamingWikiClient()

        # Cargo returns empty
        cargo_resp = MagicMock()
        cargo_resp.raise_for_status.return_value = None
        cargo_resp.json.return_value = {"cargoquery": []}

        # MediaWiki returns Apex wikitext
        wiki_resp = MagicMock()
        wiki_resp.raise_for_status.return_value = None
        wiki_resp.json.return_value = self._MEDIAWIKI_RESPONSE

        if client._session:
            monkeypatch.setattr(client._session, "get", MagicMock(side_effect=[cargo_resp, wiki_resp]))

        result = client.get_config_info("Apex Legends")
        assert result["error"] is None
        assert len(result["raw_paths"]) == 4
        assert len(result["expanded_paths"]) == 3
        # settings.cfg and videoconfig.txt should be in raw_paths
        raw_str = " ".join(result["raw_paths"])
        assert "settings.cfg" in raw_str
        assert "videoconfig.txt" in raw_str
