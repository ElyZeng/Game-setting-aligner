"""Config file reader.

Supports reading configuration files in XML, JSON, and INI formats and
returning their contents as a normalised Python dictionary.
"""

from __future__ import annotations

import configparser
import json
import os
import xml.etree.ElementTree as ET
from typing import Any, Dict


class ConfigReader:
    """Reads game configuration files into a Python dictionary."""

    def read(self, path: str) -> Dict[str, Any]:
        """Read *path* and return its contents as a dict.

        The format is inferred from the file extension.  Raises
        ``ValueError`` if the extension is not recognised and
        ``FileNotFoundError`` if the file does not exist.
        """
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Config file not found: {path}")

        ext = os.path.splitext(path)[1].lower()

        if ext == ".json":
            return self._read_json(path)
        if ext in {".xml", ".config"}:
            return self._read_xml(path)
        if ext in {".ini", ".cfg"}:
            return self._read_ini(path)

        raise ValueError(f"Unsupported config file extension: {ext!r}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_json(path: str) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)

    @staticmethod
    def _read_xml(path: str) -> Dict[str, Any]:
        tree = ET.parse(path)
        root = tree.getroot()
        return ConfigReader._element_to_dict(root)

    @staticmethod
    def _element_to_dict(element: ET.Element) -> Dict[str, Any]:
        """Recursively convert an XML element to a dict."""
        result: Dict[str, Any] = {}
        result.update(element.attrib)
        for child in element:
            child_dict = ConfigReader._element_to_dict(child)
            tag = child.tag
            if tag in result:
                if not isinstance(result[tag], list):
                    result[tag] = [result[tag]]
                result[tag].append(child_dict)
            else:
                result[tag] = child_dict
        if element.text and element.text.strip():
            result["_text"] = element.text.strip()
        return result

    @staticmethod
    def _read_ini(path: str) -> Dict[str, Any]:
        parser = configparser.ConfigParser(strict=False)
        parser.read(path, encoding="utf-8")
        result: Dict[str, Any] = {}
        for section in parser.sections():
            result[section] = dict(parser.items(section))
        # Also capture items that have no section header
        defaults = dict(parser.defaults())
        if defaults:
            result["DEFAULT"] = defaults
        return result
