"""Epic Games Store game scanner.

Detects installed Epic Games by reading the EGS manifest files located in
the ProgramData directory (Windows) or platform-equivalent paths.
"""

from __future__ import annotations

import json
import os
import sys
import glob
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class EpicGame:
    """Represents an installed Epic Games Store game."""

    app_name: str
    name: str
    install_path: str
    platform: str = "Epic"
    config_paths: List[str] = field(default_factory=list)


def _get_epic_manifests_dir() -> Optional[str]:
    """Return the directory that contains Epic Games manifest files."""
    if sys.platform == "win32":
        program_data = os.environ.get("ProgramData", "C:\\ProgramData")
        path = os.path.join(program_data, "Epic", "EpicGamesLauncher", "Data", "Manifests")
        return path if os.path.isdir(path) else None

    if sys.platform == "darwin":
        path = os.path.expanduser(
            "~/Library/Application Support/Epic/EpicGamesLauncher/Data/Manifests"
        )
        return path if os.path.isdir(path) else None

    # Linux (via Heroic or Lutris)
    candidates = [
        os.path.expanduser("~/.config/heroic/GamesConfig"),
        os.path.expanduser("~/.local/share/heroic/GamesConfig"),
    ]
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return None


def _parse_manifest(manifest_path: str) -> Optional[EpicGame]:
    """Parse a single Epic manifest (.item) file and return an EpicGame."""
    try:
        with open(manifest_path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except Exception:
        return None

    app_name = data.get("AppName", "")
    name = data.get("DisplayName", app_name)
    install_path = data.get("InstallLocation", "")

    if not app_name or not name:
        return None

    return EpicGame(
        app_name=app_name,
        name=name,
        install_path=install_path,
    )


class EpicScanner:
    """Scans the local machine for installed Epic Games Store games."""

    def scan(self) -> List[EpicGame]:
        """Return a list of installed Epic Games Store games."""
        manifests_dir = _get_epic_manifests_dir()
        if not manifests_dir:
            return []

        games: List[EpicGame] = []
        seen: set = set()

        for manifest_path in glob.glob(os.path.join(manifests_dir, "*.item")):
            game = _parse_manifest(manifest_path)
            if game and game.app_name not in seen:
                seen.add(game.app_name)
                games.append(game)

        return games
