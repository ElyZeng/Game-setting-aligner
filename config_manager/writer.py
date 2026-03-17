"""Config file writer.

Supports writing a normalised dictionary back to XML, JSON, and INI files.
"""

from __future__ import annotations

import configparser
import json
import os
import xml.etree.ElementTree as ET
from typing import Any, Dict


class ConfigWriter:
    """Writes a normalised Python dictionary to a configuration file."""

    def write(self, data: Dict[str, Any], path: str) -> None:
        """Write *data* to *path*.

        The format is inferred from the file extension.  The parent
        directory is created automatically if it does not exist.  Raises
        ``ValueError`` if the extension is not recognised.
        """
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

        ext = os.path.splitext(path)[1].lower()

        if ext == ".json":
            self._write_json(data, path)
        elif ext in {".xml", ".config"}:
            self._write_xml(data, path)
        elif ext in {".ini", ".cfg"}:
            self._write_ini(data, path)
        else:
            raise ValueError(f"Unsupported config file extension: {ext!r}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _write_json(data: Dict[str, Any], path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _write_xml(data: Dict[str, Any], path: str) -> None:
        root_tag = next(iter(data), "root")
        root_value = data.get(root_tag, {})
        root_el = ConfigWriter._dict_to_element(root_tag, root_value)
        tree = ET.ElementTree(root_el)
        ET.indent(tree, space="  ")
        tree.write(path, encoding="unicode", xml_declaration=True)

    @staticmethod
    def _dict_to_element(tag: str, value: Any) -> ET.Element:
        """Recursively convert a dict to an XML element."""
        element = ET.Element(tag)
        if isinstance(value, dict):
            text = value.get("_text")
            if text is not None:
                element.text = str(text)
            for k, v in value.items():
                if k == "_text":
                    continue
                if isinstance(v, list):
                    for item in v:
                        element.append(ConfigWriter._dict_to_element(k, item))
                elif isinstance(v, dict):
                    element.append(ConfigWriter._dict_to_element(k, v))
                else:
                    element.set(k, str(v))
        elif value is not None:
            element.text = str(value)
        return element

    @staticmethod
    def _write_ini(data: Dict[str, Any], path: str) -> None:
        parser = configparser.ConfigParser()
        for section, items in data.items():
            if section == "DEFAULT":
                for key, value in items.items():
                    parser.defaults()[key] = str(value)
            elif isinstance(items, dict):
                parser.add_section(section)
                for key, value in items.items():
                    parser.set(section, key, str(value))
        with open(path, "w", encoding="utf-8") as f:
            parser.write(f)
