"""Tests for the config_manager module."""

from __future__ import annotations

import configparser
import json
import os
import tempfile
import xml.etree.ElementTree as ET

import pytest

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_manager.reader import ConfigReader
from config_manager.writer import ConfigWriter
from config_manager.package import ConfigPackage


# ---------------------------------------------------------------------------
# ConfigReader tests
# ---------------------------------------------------------------------------

class TestConfigReaderJSON:
    def test_read_json(self, tmp_path):
        data = {"key": "value", "number": 42}
        p = tmp_path / "config.json"
        p.write_text(json.dumps(data), encoding="utf-8")

        result = ConfigReader().read(str(p))
        assert result == data

    def test_read_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ConfigReader().read(str(tmp_path / "nonexistent.json"))

    def test_unsupported_extension_raises(self, tmp_path):
        p = tmp_path / "config.toml"
        p.write_text("[section]\nkey=val")
        with pytest.raises(ValueError):
            ConfigReader().read(str(p))


class TestConfigReaderXML:
    def test_read_xml(self, tmp_path):
        xml_content = """<?xml version='1.0' encoding='utf-8'?>
<root>
  <option name="fullscreen">true</option>
</root>"""
        p = tmp_path / "config.xml"
        p.write_text(xml_content, encoding="utf-8")

        result = ConfigReader().read(str(p))
        assert "option" in result


class TestConfigReaderINI:
    def test_read_ini(self, tmp_path):
        ini_content = "[Graphics]\nresolution=1920x1080\nvsync=true\n"
        p = tmp_path / "config.ini"
        p.write_text(ini_content, encoding="utf-8")

        result = ConfigReader().read(str(p))
        assert "Graphics" in result
        assert result["Graphics"]["resolution"] == "1920x1080"

    def test_read_cfg_extension(self, tmp_path):
        ini_content = "[Audio]\nvolume=80\n"
        p = tmp_path / "config.cfg"
        p.write_text(ini_content, encoding="utf-8")

        result = ConfigReader().read(str(p))
        assert "Audio" in result


# ---------------------------------------------------------------------------
# ConfigWriter tests
# ---------------------------------------------------------------------------

class TestConfigWriterJSON:
    def test_write_json(self, tmp_path):
        data = {"resolution": "1080p", "vsync": True}
        p = tmp_path / "out.json"

        ConfigWriter().write(data, str(p))

        with open(p, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == data

    def test_write_creates_parent_dirs(self, tmp_path):
        data = {"x": 1}
        p = tmp_path / "nested" / "dir" / "out.json"
        ConfigWriter().write(data, str(p))
        assert p.exists()

    def test_unsupported_extension_raises(self, tmp_path):
        p = tmp_path / "out.toml"
        with pytest.raises(ValueError):
            ConfigWriter().write({}, str(p))


class TestConfigWriterINI:
    def test_write_ini(self, tmp_path):
        data = {"Graphics": {"resolution": "1920x1080"}}
        p = tmp_path / "out.ini"

        ConfigWriter().write(data, str(p))

        parser = configparser.ConfigParser()
        parser.read(str(p))
        assert parser["Graphics"]["resolution"] == "1920x1080"


class TestConfigWriterXML:
    def test_write_xml(self, tmp_path):
        data = {"root": {"_text": "hello"}}
        p = tmp_path / "out.xml"

        ConfigWriter().write(data, str(p))
        tree = ET.parse(str(p))
        root = tree.getroot()
        assert root.tag == "root"
        assert root.text == "hello"


# ---------------------------------------------------------------------------
# ConfigPackage tests
# ---------------------------------------------------------------------------

class TestConfigPackage:
    def test_export_and_import_json(self, tmp_path):
        # Create a dummy config file
        cfg_file = tmp_path / "game_config.json"
        cfg_data = {"brightness": 80, "fullscreen": True}
        cfg_file.write_text(json.dumps(cfg_data), encoding="utf-8")

        package_path = str(tmp_path / "backup.json")

        pkg = ConfigPackage()
        pkg.export({"MyGame": [str(cfg_file)]}, package_path)

        assert os.path.isfile(package_path)

        # Modify the original file
        cfg_file.write_text(json.dumps({"brightness": 50}), encoding="utf-8")

        # Import should restore the original values
        restored = pkg.import_package(package_path)
        assert "MyGame" in restored

        with open(cfg_file, encoding="utf-8") as f:
            result = json.load(f)
        assert result["brightness"] == 80
        assert result["fullscreen"] is True

    def test_export_skips_missing_files(self, tmp_path):
        package_path = str(tmp_path / "backup.json")
        pkg = ConfigPackage()
        pkg.export({"MyGame": ["/nonexistent/path/config.json"]}, package_path)

        with open(package_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["games"]["MyGame"] == {}

    def test_import_missing_package_raises(self, tmp_path):
        pkg = ConfigPackage()
        with pytest.raises(FileNotFoundError):
            pkg.import_package(str(tmp_path / "missing.json"))

    def test_import_wrong_version_raises(self, tmp_path):
        bad_package = tmp_path / "bad.json"
        bad_package.write_text(json.dumps({"version": 999, "games": {}}))
        pkg = ConfigPackage()
        with pytest.raises(ValueError):
            pkg.import_package(str(bad_package))
