"""GOG Galaxy game scanner.

Detects installed GOG games by reading GOG Galaxy database or registry keys.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class GOGGame:
    """Represents an installed GOG game."""

    game_id: str
    name: str
    install_path: str
    platform: str = "GOG"
    config_paths: List[str] = field(default_factory=list)


def _get_gog_games_windows() -> List[GOGGame]:
    """Read installed GOG games from the Windows registry."""
    games: List[GOGGame] = []
    try:
        import winreg  # type: ignore

        key_paths = [
            r"SOFTWARE\GOG.com\Games",
            r"SOFTWARE\WOW6432Node\GOG.com\Games",
        ]
        for key_path in key_paths:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as parent:
                    index = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(parent, index)
                            index += 1
                            with winreg.OpenKey(parent, subkey_name) as subkey:
                                try:
                                    game_name, _ = winreg.QueryValueEx(subkey, "GAMENAME")
                                    install_path, _ = winreg.QueryValueEx(subkey, "PATH")
                                    game_id, _ = winreg.QueryValueEx(subkey, "PRODUCTID")
                                    games.append(
                                        GOGGame(
                                            game_id=str(game_id),
                                            name=game_name,
                                            install_path=install_path,
                                        )
                                    )
                                except FileNotFoundError:
                                    pass
                        except OSError:
                            break
            except FileNotFoundError:
                continue
    except ImportError:
        pass
    return games


def _get_gog_games_linux() -> List[GOGGame]:
    """Read installed GOG games from GOG Galaxy 2 database on Linux."""
    games: List[GOGGame] = []

    # GOG Galaxy 2 stores a SQLite database
    db_path = os.path.expanduser("~/.local/share/gog-galaxy-2/storage/galaxy.db")
    if not os.path.isfile(db_path):
        return games

    try:
        import sqlite3

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT releaseKey, title, installationPath FROM InstalledExternalProducts"
        )
        for row in cursor.fetchall():
            release_key, title, install_path = row
            games.append(
                GOGGame(
                    game_id=str(release_key),
                    name=title or str(release_key),
                    install_path=install_path or "",
                )
            )
        conn.close()
    except Exception:
        pass

    return games


class GOGScanner:
    """Scans the local machine for installed GOG games."""

    def scan(self) -> List[GOGGame]:
        """Return a list of installed GOG games."""
        if sys.platform == "win32":
            return _get_gog_games_windows()
        if sys.platform == "linux":
            return _get_gog_games_linux()
        return []
