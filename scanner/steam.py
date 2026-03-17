"""Steam game scanner.

Detects installed Steam games by reading the Steam library folders from
VDF/ACF manifest files and (on Windows) the Windows registry.
"""

from __future__ import annotations

import os
import sys
import glob
from dataclasses import dataclass, field
from typing import List, Optional

try:
    import vdf  # type: ignore
except ImportError:  # pragma: no cover
    vdf = None  # type: ignore


@dataclass
class SteamGame:
    """Represents an installed Steam game."""

    app_id: str
    name: str
    install_path: str
    platform: str = "Steam"
    config_paths: List[str] = field(default_factory=list)


def _get_steam_install_path_windows() -> Optional[str]:
    """Return the Steam installation path from the Windows registry."""
    try:
        import winreg  # type: ignore

        key_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam"),
        ]
        for hive, key_path in key_paths:
            try:
                with winreg.OpenKey(hive, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, "InstallPath")
                    if value and os.path.isdir(value):
                        return value
            except FileNotFoundError:
                continue
    except ImportError:
        pass
    return None


def _get_steam_install_path() -> Optional[str]:
    """Return the Steam installation path for the current platform."""
    if sys.platform == "win32":
        path = _get_steam_install_path_windows()
        if path:
            return path
        # Fallback default location
        default = os.path.join(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"), "Steam")
        return default if os.path.isdir(default) else None

    if sys.platform == "darwin":
        path = os.path.expanduser("~/Library/Application Support/Steam")
        return path if os.path.isdir(path) else None

    # Linux
    candidates = [
        os.path.expanduser("~/.local/share/Steam"),
        os.path.expanduser("~/.steam/steam"),
        os.path.expanduser("~/.steam/root"),
    ]
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return None


def _parse_library_folders(steam_path: str) -> List[str]:
    """Parse libraryfolders.vdf to find all Steam library paths."""
    library_paths: List[str] = []

    vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if not os.path.isfile(vdf_path):
        return library_paths

    if vdf is None:
        return library_paths

    try:
        with open(vdf_path, "r", encoding="utf-8", errors="replace") as f:
            data = vdf.load(f)
    except Exception:
        return library_paths

    folders = data.get("libraryfolders", data.get("LibraryFolders", {}))
    for key, value in folders.items():
        if key.isdigit():
            if isinstance(value, dict):
                path = value.get("path", "")
            else:
                path = str(value)
            if path and os.path.isdir(path):
                library_paths.append(path)

    return library_paths


def _parse_acf(acf_path: str) -> Optional[SteamGame]:
    """Parse a single appmanifest ACF file and return a SteamGame or None."""
    if vdf is None:
        return None

    try:
        with open(acf_path, "r", encoding="utf-8", errors="replace") as f:
            data = vdf.load(f)
    except Exception:
        return None

    state = data.get("AppState", {})
    app_id = str(state.get("appid", ""))
    name = state.get("name", "")
    install_dir = state.get("installdir", "")

    if not app_id or not name:
        return None

    # Resolve the actual install path
    steamapps_dir = os.path.dirname(acf_path)
    install_path = os.path.join(steamapps_dir, "common", install_dir)

    return SteamGame(
        app_id=app_id,
        name=name,
        install_path=install_path,
    )


class SteamScanner:
    """Scans the local machine for installed Steam games."""

    def scan(self) -> List[SteamGame]:
        """Return a list of installed Steam games."""
        steam_path = _get_steam_install_path()
        if not steam_path:
            return []

        library_paths = _parse_library_folders(steam_path)
        # Always include the main Steam directory
        if steam_path not in library_paths:
            library_paths.insert(0, steam_path)

        games: List[SteamGame] = []
        seen_ids: set = set()

        for lib_path in library_paths:
            steamapps_dir = os.path.join(lib_path, "steamapps")
            if not os.path.isdir(steamapps_dir):
                continue
            for acf_path in glob.glob(os.path.join(steamapps_dir, "appmanifest_*.acf")):
                game = _parse_acf(acf_path)
                if game and game.app_id not in seen_ids:
                    seen_ids.add(game.app_id)
                    games.append(game)

        return games
