"""Config package serialisation.

Provides ConfigPackage which bundles multiple game configuration files into
a single JSON archive for backup / transfer, and restores them from one.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from .reader import ConfigReader
from .writer import ConfigWriter


class ConfigPackage:
    """Bundle and restore game configuration files.

    The package format is a JSON file with the following structure::

        {
            "version": 1,
            "games": {
                "<game_name>": {
                    "<original_path>": <config_data_dict>,
                    ...
                },
                ...
            }
        }
    """

    SUPPORTED_VERSIONS = {1, 2}

    def __init__(self) -> None:
        self._reader = ConfigReader()
        self._writer = ConfigWriter()

    def export(self, game_configs: Dict[str, List[str]], output_path: str) -> None:
        """Export configuration files for multiple games to *output_path*.

        Parameters
        ----------
        game_configs:
            A mapping of game name → list of absolute config file paths.
        output_path:
            Destination path for the generated JSON package (e.g.
            ``backup.json``).
        """
        package: Dict[str, Any] = {
            "version": 1,
            "games": {},
        }

        for game_name, paths in game_configs.items():
            game_data: Dict[str, Any] = {}
            for config_path in paths:
                if not os.path.isfile(config_path):
                    continue
                try:
                    data = self._reader.read(config_path)
                    game_data[config_path] = data
                except Exception as exc:
                    game_data[config_path] = {"_error": str(exc)}
            package["games"][game_name] = game_data

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(package, f, indent=2, ensure_ascii=False)

    def import_package(self, package_path: str) -> Dict[str, List[str]]:
        """Restore configuration files from a package created by :meth:`export`.

        Each configuration file is written back to its original absolute path.
        Returns a mapping of game name → list of restored file paths.

        Raises ``FileNotFoundError`` if *package_path* does not exist.
        Raises ``ValueError`` if the package version is unsupported.
        """
        if not os.path.isfile(package_path):
            raise FileNotFoundError(f"Package not found: {package_path}")

        with open(package_path, "r", encoding="utf-8") as f:
            package: Dict[str, Any] = json.load(f)

        pkg_version = package.get("version")
        if pkg_version not in self.SUPPORTED_VERSIONS:
            raise ValueError(
                f"Unsupported package version: {pkg_version}"
            )

        if pkg_version == 2:
            return self._import_v2(package)

        restored: Dict[str, List[str]] = {}
        for game_name, game_data in package.get("games", {}).items():
            restored_paths: List[str] = []
            for config_path, data in game_data.items():
                if "_error" in data:
                    continue
                try:
                    self._writer.write(data, config_path)
                    restored_paths.append(config_path)
                except Exception:
                    pass
            restored[game_name] = restored_paths

        return restored

    def _import_v2(self, package: Dict[str, Any]) -> Dict[str, List[str]]:
        """Restore config files from a version-2 package (ConfigExporter format).

        Version 2 stores each config file as a dict with ``expanded_path``,
        ``content``, ``found``, ``error``, and optionally ``type`` keys.
        Registry entries are skipped (cannot be written back easily).
        """
        restored: Dict[str, List[str]] = {}
        for game_name, game_data in package.get("games", {}).items():
            restored_paths: List[str] = []
            config_files = game_data.get("config_files", [])
            for cfg in config_files:
                # Skip registry entries – we can't write back to the registry
                if cfg.get("type") == "registry":
                    continue
                path = cfg.get("expanded_path", "")
                content = cfg.get("content")
                if not path or not content:
                    continue
                if cfg.get("error"):
                    continue
                try:
                    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(content)
                    restored_paths.append(path)
                except Exception:
                    pass
            restored[game_name] = restored_paths

        return restored
