"""Tests for config_manager.config_exporter module."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_manager.config_exporter import ConfigExporter, _MAX_FILE_BYTES, _try_read_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeGame:
    """Minimal game object compatible with ConfigExporter.export()."""

    def __init__(self, name: str, install_path: str = "", platform: str = "Steam") -> None:
        self.name = name
        self.install_path = install_path
        self.platform = platform


def _make_wiki_mock(raw_paths=None, expanded_paths=None, error=None):
    """Return a mock wiki client whose get_config_info() returns given values."""
    mock = MagicMock()
    mock.get_config_info.return_value = {
        "page_title": "FakeGame",
        "url": "https://www.pcgamingwiki.com/wiki/FakeGame",
        "raw_paths": raw_paths or [],
        "expanded_paths": expanded_paths or [],
        "error": error,
    }
    return mock


# ---------------------------------------------------------------------------
# _try_read_file tests
# ---------------------------------------------------------------------------

class TestTryReadFile:
    def test_reads_existing_file(self, tmp_path):
        cfg = tmp_path / "settings.cfg"
        cfg.write_text("setting=1\nresolution=1080p", encoding="utf-8")
        result = _try_read_file(str(cfg))

        assert result["found"] is True
        assert result["content"] == "setting=1\nresolution=1080p"
        assert result["truncated"] is False
        assert result["error"] is None

    def test_missing_file_returns_not_found(self, tmp_path):
        result = _try_read_file(str(tmp_path / "nonexistent.cfg"))

        assert result["found"] is False
        assert result["error"] == "path_not_found"
        assert result["content"] is None

    def test_truncates_large_file(self, tmp_path):
        large_file = tmp_path / "big.cfg"
        # Write slightly more than the limit
        large_file.write_bytes(b"x" * (_MAX_FILE_BYTES + 100))
        result = _try_read_file(str(large_file))

        assert result["found"] is True
        assert result["truncated"] is True
        assert result["content"] is not None
        assert len(result["content"].encode("utf-8")) <= _MAX_FILE_BYTES

    def test_expanded_path_is_recorded(self, tmp_path):
        cfg = tmp_path / "config.ini"
        cfg.write_text("[s]\nk=v", encoding="utf-8")
        result = _try_read_file(str(cfg))

        assert result["expanded_path"] == str(cfg)

    def test_file_within_size_limit_not_truncated(self, tmp_path):
        cfg = tmp_path / "small.json"
        cfg.write_text('{"key": "value"}', encoding="utf-8")
        result = _try_read_file(str(cfg))

        assert result["truncated"] is False


# ---------------------------------------------------------------------------
# ConfigExporter tests
# ---------------------------------------------------------------------------

class TestConfigExporterNoWiki:
    def test_export_creates_json_file(self, tmp_path):
        exporter = ConfigExporter(wiki_client=None)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("MyGame", "/games/mygame")], output)

        assert os.path.isfile(output)

    def test_export_format_version(self, tmp_path):
        exporter = ConfigExporter(wiki_client=None)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("MyGame")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)
        assert data["version"] == ConfigExporter.FORMAT_VERSION

    def test_export_game_entry_structure(self, tmp_path):
        exporter = ConfigExporter(wiki_client=None)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("MyGame", "/games/mygame", "Steam")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        assert "MyGame" in data["games"]
        game = data["games"]["MyGame"]
        assert game["detected_install_path"] == "/games/mygame"
        assert game["platform"] == "Steam"
        assert game["pcgamingwiki"] is None
        assert game["config_files"] == []

    def test_export_multiple_games(self, tmp_path):
        exporter = ConfigExporter(wiki_client=None)
        output = str(tmp_path / "out.json")
        games = [_FakeGame("GameA"), _FakeGame("GameB")]
        exporter.export(games, output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)
        assert set(data["games"].keys()) == {"GameA", "GameB"}

    def test_export_creates_parent_dirs(self, tmp_path):
        exporter = ConfigExporter(wiki_client=None)
        output = str(tmp_path / "nested" / "dir" / "out.json")
        exporter.export([_FakeGame("GameA")], output)

        assert os.path.isfile(output)


class TestConfigExporterWithWiki:
    def test_export_pcgamingwiki_section_populated(self, tmp_path):
        mock_wiki = _make_wiki_mock(
            raw_paths=[r"%USERPROFILE%\Saved Games\Game\settings.cfg"],
            expanded_paths=[os.path.join(os.path.expanduser("~"), "Saved Games", "Game", "settings.cfg")],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        wiki = data["games"]["Game"]["pcgamingwiki"]
        assert wiki is not None
        assert wiki["error"] is None
        assert len(wiki["raw_paths"]) == 1
        assert len(wiki["expanded_paths"]) == 1

    def test_export_config_files_not_found(self, tmp_path):
        expanded = os.path.join(os.path.expanduser("~"), "Saved Games", "Game", "settings.cfg")
        mock_wiki = _make_wiki_mock(
            raw_paths=[r"%USERPROFILE%\Saved Games\Game\settings.cfg"],
            expanded_paths=[expanded],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        cfg_files = data["games"]["Game"]["config_files"]
        assert len(cfg_files) == 1
        entry = cfg_files[0]
        assert entry["found"] is False
        assert entry["error"] == "path_not_found"

    def test_export_config_file_read_when_exists(self, tmp_path):
        cfg_file = tmp_path / "settings.cfg"
        cfg_file.write_text("volume=80\nresolution=1920x1080", encoding="utf-8")

        mock_wiki = _make_wiki_mock(
            raw_paths=[r"%USERPROFILE%\Game\settings.cfg"],
            expanded_paths=[str(cfg_file)],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        cfg_files = data["games"]["Game"]["config_files"]
        assert len(cfg_files) == 1
        entry = cfg_files[0]
        assert entry["found"] is True
        assert "volume=80" in entry["content"]
        assert entry["error"] is None
        assert entry["truncated"] is False

    def test_wiki_error_recorded_in_json(self, tmp_path):
        mock_wiki = MagicMock()
        mock_wiki.get_config_info.side_effect = Exception("network error")

        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)  # must not raise

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        wiki = data["games"]["Game"]["pcgamingwiki"]
        assert wiki["error"] is not None
        assert data["games"]["Game"]["config_files"] == []

    def test_wiki_error_field_propagated(self, tmp_path):
        mock_wiki = _make_wiki_mock(error="API quota exceeded")
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        assert data["games"]["Game"]["pcgamingwiki"]["error"] == "API quota exceeded"

    def test_get_config_info_called_with_game_name(self, tmp_path):
        mock_wiki = _make_wiki_mock()
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Apex Legends")], output)

        mock_wiki.get_config_info.assert_called_once_with("Apex Legends")


# ---------------------------------------------------------------------------
# Imports for new helpers
# ---------------------------------------------------------------------------

from config_manager.config_exporter import (
    _is_steam_userdata_path,
    _scan_directory,
    _DIR_SCAN_DEPTH,
    _CONFIG_EXTENSIONS,
)


# ---------------------------------------------------------------------------
# _is_steam_userdata_path tests
# ---------------------------------------------------------------------------

class TestIsSteamUserdataPath:
    def test_userdata_windows_backslash(self):
        path = r"C:\Program Files (x86)\Steam\userdata\12345\553850\remote\input.config"
        assert _is_steam_userdata_path(path) is True

    def test_userdata_forward_slash(self):
        path = "/home/user/.steam/steam/userdata/12345/553850/remote/input.config"
        assert _is_steam_userdata_path(path) is True

    def test_non_userdata_path(self):
        path = r"C:\Users\user\AppData\Roaming\App\settings.cfg"
        assert _is_steam_userdata_path(path) is False

    def test_empty_path(self):
        assert _is_steam_userdata_path("") is False

    def test_path_contains_userdata_word_not_as_segment(self):
        # 'userdata' not flanked by slashes should still be caught if surrounded
        path = r"C:\Steam\userdata\123\game\file.cfg"
        assert _is_steam_userdata_path(path) is True


# ---------------------------------------------------------------------------
# _scan_directory tests
# ---------------------------------------------------------------------------

class TestScanDirectory:
    def test_finds_config_file_at_depth_0(self, tmp_path):
        cfg = tmp_path / "settings.cfg"
        cfg.write_text("k=v", encoding="utf-8")
        found = _scan_directory(str(tmp_path), max_depth=0)
        assert str(cfg) in found

    def test_ignores_unknown_extension(self, tmp_path):
        (tmp_path / "readme.md").write_text("hello", encoding="utf-8")
        found = _scan_directory(str(tmp_path), max_depth=0)
        assert found == []

    def test_scans_depth_1(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        cfg = sub / "options.ini"
        cfg.write_text("[s]\nk=v", encoding="utf-8")
        found = _scan_directory(str(tmp_path), max_depth=1)
        assert str(cfg) in found

    def test_does_not_exceed_max_depth(self, tmp_path):
        """Files at depth 3 must NOT appear when max_depth=2."""
        d1 = tmp_path / "a"
        d2 = d1 / "b"
        d3 = d2 / "c"
        d3.mkdir(parents=True)
        deep_cfg = d3 / "deep.cfg"
        deep_cfg.write_text("deep", encoding="utf-8")
        found = _scan_directory(str(tmp_path), max_depth=2)
        assert str(deep_cfg) not in found

    def test_depth_2_default_finds_two_levels_deep(self, tmp_path):
        """Files at depth ≤ 2 must be found with the default depth."""
        d1 = tmp_path / "a"
        d2 = d1 / "b"
        d2.mkdir(parents=True)
        cfg = d2 / "game.cfg"
        cfg.write_text("cfg", encoding="utf-8")
        found = _scan_directory(str(tmp_path))  # uses default _DIR_SCAN_DEPTH == 2
        assert str(cfg) in found

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        found = _scan_directory(str(tmp_path / "nonexistent"))
        assert found == []

    def test_all_config_extensions_found(self, tmp_path):
        for ext in _CONFIG_EXTENSIONS:
            (tmp_path / f"file{ext}").write_text("x", encoding="utf-8")
        found = _scan_directory(str(tmp_path), max_depth=0)
        assert len(found) == len(_CONFIG_EXTENSIONS)

    def test_default_depth_constant(self):
        assert _DIR_SCAN_DEPTH == 2


# ---------------------------------------------------------------------------
# ConfigExporter – userdata exclusion and directory scanning
# ---------------------------------------------------------------------------

class TestConfigExporterUserdataExclusion:
    def test_userdata_path_excluded_from_config_files(self, tmp_path):
        """Steam userdata path must not appear in config_files."""
        userdata_path = r"C:\Steam\userdata\12345\553850\remote\input.config"
        normal_path = str(tmp_path / "settings.cfg")
        (tmp_path / "settings.cfg").write_text("v=1", encoding="utf-8")

        mock_wiki = _make_wiki_mock(
            raw_paths=[userdata_path, normal_path],
            expanded_paths=[userdata_path, normal_path],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        game = data["games"]["Game"]
        # expanded_paths still contains userdata path (diagnostic)
        assert any("userdata" in p.lower() for p in game["pcgamingwiki"]["expanded_paths"])
        # config_files must NOT contain the Steam userdata entry
        cfg_paths = [e["expanded_path"] for e in game["config_files"]]
        assert userdata_path not in cfg_paths

    def test_userdata_path_present_in_expanded_paths(self, tmp_path):
        """Steam userdata path must remain in pcgamingwiki.expanded_paths."""
        userdata_path = r"C:\Steam\userdata\12345\553850\remote\input.config"
        mock_wiki = _make_wiki_mock(
            raw_paths=[userdata_path],
            expanded_paths=[userdata_path],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        game = data["games"]["Game"]
        assert userdata_path in game["pcgamingwiki"]["expanded_paths"]
        assert game["config_files"] == []

    def test_non_userdata_path_included_in_config_files(self, tmp_path):
        """Non-userdata expanded path must still be read into config_files."""
        cfg = tmp_path / "settings.cfg"
        cfg.write_text("volume=80", encoding="utf-8")
        mock_wiki = _make_wiki_mock(
            raw_paths=[str(cfg)],
            expanded_paths=[str(cfg)],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        cfg_files = data["games"]["Game"]["config_files"]
        assert len(cfg_files) == 1
        assert cfg_files[0]["found"] is True


class TestConfigExporterDirectoryScan:
    def test_directory_path_triggers_scan(self, tmp_path):
        """When an expanded path is a directory, its config files are included."""
        game_dir = tmp_path / "GameProfile"
        game_dir.mkdir()
        (game_dir / "settings.ini").write_text("[s]\nk=v", encoding="utf-8")
        (game_dir / "save.sav").write_text("binary", encoding="utf-8")  # ignored ext

        mock_wiki = _make_wiki_mock(
            raw_paths=[str(game_dir)],
            expanded_paths=[str(game_dir)],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        cfg_files = data["games"]["Game"]["config_files"]
        assert len(cfg_files) == 1
        assert "settings.ini" in cfg_files[0]["expanded_path"]

    def test_directory_scan_depth_2(self, tmp_path):
        """Files two levels deep inside a directory path are found."""
        profile = tmp_path / "Profile"
        nested = profile / "sub1" / "sub2"
        nested.mkdir(parents=True)
        (nested / "options.cfg").write_text("opt=1", encoding="utf-8")

        mock_wiki = _make_wiki_mock(
            raw_paths=[str(profile)],
            expanded_paths=[str(profile)],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        cfg_files = data["games"]["Game"]["config_files"]
        paths = [e["expanded_path"] for e in cfg_files]
        assert any("options.cfg" in p for p in paths)

    def test_directory_scan_beyond_depth_2_excluded(self, tmp_path):
        """Files 3 levels deep must NOT appear in config_files."""
        profile = tmp_path / "Profile"
        deep = profile / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "deep.cfg").write_text("d=1", encoding="utf-8")

        mock_wiki = _make_wiki_mock(
            raw_paths=[str(profile)],
            expanded_paths=[str(profile)],
        )
        exporter = ConfigExporter(wiki_client=mock_wiki)
        output = str(tmp_path / "out.json")
        exporter.export([_FakeGame("Game")], output)

        with open(output, encoding="utf-8") as f:
            data = json.load(f)

        cfg_files = data["games"]["Game"]["config_files"]
        paths = [e["expanded_path"] for e in cfg_files]
        assert not any("deep.cfg" in p for p in paths)
