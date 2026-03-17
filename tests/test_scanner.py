"""Tests for the scanner module."""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scanner.epic import EpicScanner, _parse_manifest
from scanner.steam import SteamGame, _parse_library_folders
from scanner.gog import GOGGame


# ---------------------------------------------------------------------------
# Steam scanner tests
# ---------------------------------------------------------------------------

class TestSteamScanner:
    def test_parse_library_folders_missing_file(self, tmp_path):
        """Should return empty list when libraryfolders.vdf does not exist."""
        result = _parse_library_folders(str(tmp_path))
        assert result == []

    def test_steam_game_dataclass(self):
        game = SteamGame(app_id="123", name="Test Game", install_path="/games/test")
        assert game.platform == "Steam"
        assert game.config_paths == []

    def test_scan_returns_list(self):
        """SteamScanner.scan() must return a list (possibly empty)."""
        from scanner.steam import SteamScanner
        result = SteamScanner().scan()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Epic Games scanner tests
# ---------------------------------------------------------------------------

class TestEpicScanner:
    def test_parse_manifest_valid(self, tmp_path):
        manifest = {
            "AppName": "fortnite",
            "DisplayName": "Fortnite",
            "InstallLocation": "/games/Fortnite",
        }
        p = tmp_path / "fortnite.item"
        p.write_text(json.dumps(manifest), encoding="utf-8")

        game = _parse_manifest(str(p))
        assert game is not None
        assert game.name == "Fortnite"
        assert game.app_name == "fortnite"
        assert game.install_path == "/games/Fortnite"
        assert game.platform == "Epic"

    def test_parse_manifest_invalid_json(self, tmp_path):
        p = tmp_path / "broken.item"
        p.write_text("not json content", encoding="utf-8")

        result = _parse_manifest(str(p))
        assert result is None

    def test_parse_manifest_missing_app_name(self, tmp_path):
        manifest = {"DisplayName": "SomeGame", "InstallLocation": "/games/x"}
        p = tmp_path / "missing_app.item"
        p.write_text(json.dumps(manifest), encoding="utf-8")

        result = _parse_manifest(str(p))
        assert result is None

    def test_scan_no_manifests_dir(self):
        """EpicScanner.scan() returns empty list when no manifests dir exists."""
        scanner = EpicScanner()
        # On most CI environments there's no Epic installed
        result = scanner.scan()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# GOG scanner tests
# ---------------------------------------------------------------------------

class TestGOGScanner:
    def test_gog_game_dataclass(self):
        game = GOGGame(game_id="12345", name="The Witcher 3", install_path="/games/tw3")
        assert game.platform == "GOG"
        assert game.config_paths == []

    def test_scan_returns_list(self):
        from scanner.gog import GOGScanner
        result = GOGScanner().scan()
        assert isinstance(result, list)
