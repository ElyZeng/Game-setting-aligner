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
