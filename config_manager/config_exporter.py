"""Enhanced config exporter with PCGamingWiki integration.

Exports game configuration metadata — including PCGamingWiki-sourced config
file paths and their local content — into a structured JSON package.
"""

from __future__ import annotations

import json
import os
import platform
from typing import Any, Dict, List, Optional

if platform.system() == "Windows":
    import winreg
else:
    winreg = None  # type: ignore[assignment]

# Maximum bytes to read from a single config file (512 KB)
_MAX_FILE_BYTES = 512 * 1024

# Byte threshold for binary detection: if more than this fraction of a
# sample contains non-text bytes, the file is treated as binary.
_BINARY_CHECK_SIZE = 8192
_BINARY_THRESHOLD = 0.10

# Extensions treated as config/settings files when scanning directories
_CONFIG_EXTENSIONS = frozenset(
    {".ini", ".cfg", ".config", ".json", ".xml", ".txt",
     ".dat", ".vcfg", ".toml", ".yaml", ".yml"}
)

# Default maximum directory scan depth
_DIR_SCAN_DEPTH = 2

# Registry root key name → winreg constant mapping
_REGISTRY_ROOTS: Dict[str, Any] = {}
if winreg is not None:
    _REGISTRY_ROOTS = {
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
        "HKEY_CLASSES_ROOT": winreg.HKEY_CLASSES_ROOT,
        "HKEY_USERS": winreg.HKEY_USERS,
        "HKEY_CURRENT_CONFIG": winreg.HKEY_CURRENT_CONFIG,
    }


def _is_expanded_registry_path(path: str) -> bool:
    """Return ``True`` if *path* is an expanded Windows registry path."""
    return any(path.startswith(root) for root in _REGISTRY_ROOTS)


def _read_registry_key(reg_path: str) -> Dict[str, Any]:
    """Read all values under a Windows registry key.

    Returns a dict with ``found``, ``content`` (dict of value-name → value),
    and ``error`` keys.
    """
    entry: Dict[str, Any] = {
        "type": "registry",
        "registry_path": reg_path,
        "found": False,
        "content": None,
        "error": None,
    }
    if winreg is None:
        entry["error"] = "registry_not_available"
        return entry

    # Parse root key and subkey
    parts = reg_path.split("\\", 1)
    root_name = parts[0]
    subkey = parts[1] if len(parts) > 1 else ""

    root_handle = _REGISTRY_ROOTS.get(root_name)
    if root_handle is None:
        entry["error"] = f"unknown_root_key: {root_name}"
        return entry

    # Try the exact subkey first, then enumerate sub-keys one level deep
    all_values: Dict[str, Any] = {}
    found_any = False

    # Read values from the key itself
    try:
        with winreg.OpenKey(root_handle, subkey, 0, winreg.KEY_READ) as key:
            found_any = True
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    all_values[name or "(Default)"] = value
                    i += 1
                except OSError:
                    break
    except FileNotFoundError:
        pass
    except PermissionError:
        entry["error"] = "permission_denied"
        return entry

    # Enumerate immediate sub-keys and read their values too
    try:
        with winreg.OpenKey(root_handle, subkey, 0, winreg.KEY_READ) as key:
            sub_idx = 0
            while True:
                try:
                    sub_name = winreg.EnumKey(key, sub_idx)
                    sub_idx += 1
                    sub_values: Dict[str, Any] = {}
                    try:
                        with winreg.OpenKey(key, sub_name, 0, winreg.KEY_READ) as sk:
                            j = 0
                            while True:
                                try:
                                    vname, vval, _ = winreg.EnumValue(sk, j)
                                    sub_values[vname or "(Default)"] = vval
                                    j += 1
                                except OSError:
                                    break
                    except (FileNotFoundError, PermissionError):
                        pass
                    if sub_values:
                        all_values[sub_name] = sub_values
                        found_any = True
                except OSError:
                    break
    except (FileNotFoundError, PermissionError):
        pass

    if found_any:
        entry["found"] = True
        entry["content"] = json.dumps(all_values, indent=2, ensure_ascii=False, default=str)
    else:
        entry["error"] = "key_not_found"

    return entry


def _is_binary_file(path: str) -> bool:
    """Return ``True`` if *path* appears to be a binary (non-text) file."""
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(_BINARY_CHECK_SIZE)
        if not chunk:
            return False
        # Count bytes that are not printable ASCII / common whitespace
        non_text = sum(1 for b in chunk if b < 8 or (13 < b < 32 and b != 27))
        return (non_text / len(chunk)) > _BINARY_THRESHOLD
    except OSError:
        return False


def _try_read_file(path: str) -> Dict[str, Any]:
    """Attempt to read a config file and return a structured result dict.

    The returned dict always contains:

    ``expanded_path``
        The absolute path that was attempted.
    ``found``
        ``True`` if the file exists (even if it could not be read).
    ``content``
        Text content of the file, or ``None`` if unavailable.
    ``truncated``
        ``True`` if the file was larger than :data:`_MAX_FILE_BYTES` and only
        a prefix was read.
    ``error``
        ``None`` on success, or a short error token / message string.
    """
    entry: Dict[str, Any] = {
        "expanded_path": path,
        "found": False,
        "content": None,
        "truncated": False,
        "error": None,
    }
    try:
        if not os.path.isfile(path):
            entry["error"] = "path_not_found"
            return entry
        entry["found"] = True
        if _is_binary_file(path):
            entry["error"] = "binary_file"
            return entry
        size = os.path.getsize(path)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            if size > _MAX_FILE_BYTES:
                entry["content"] = fh.read(_MAX_FILE_BYTES)
                entry["truncated"] = True
            else:
                entry["content"] = fh.read()
    except PermissionError:
        entry["error"] = "permission_denied"
    except OSError as exc:
        entry["error"] = str(exc)
    return entry


def _is_steam_userdata_path(path: str) -> bool:
    """Return ``True`` if *path* resides under a Steam ``userdata`` directory.

    Steam userdata paths are kept in ``pcgamingwiki.expanded_paths`` for
    diagnostics but are excluded from ``config_files`` by default (decision
    1a).
    """
    # Normalise to forward slashes for a simple substring check
    normalised = path.replace("\\", "/").lower()
    return "/userdata/" in normalised


def _scan_directory(dir_path: str, max_depth: int = _DIR_SCAN_DEPTH) -> List[str]:
    """Recursively scan *dir_path* for config-like files up to *max_depth*.

    Parameters
    ----------
    dir_path:
        Absolute path to the directory to scan.
    max_depth:
        Maximum recursion depth.  ``0`` scans only the immediate children of
        *dir_path*; ``2`` (default) descends two levels deeper.

    Returns
    -------
    list[str]
        Absolute paths of matching files whose extension is in
        :data:`_CONFIG_EXTENSIONS`.
    """
    found: List[str] = []

    def _recurse(path: str, depth: int) -> None:
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        if depth > 0:
                            _recurse(entry.path, depth - 1)
                        continue
                    if entry.is_file(follow_symlinks=False):
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in _CONFIG_EXTENSIONS:
                            found.append(entry.path)
                        elif ext == "":
                            # Extensionless file: include if it is a text file
                            # (not binary) and small enough.
                            try:
                                size = entry.stat().st_size
                                if 0 < size <= _MAX_FILE_BYTES and not _is_binary_file(entry.path):
                                    found.append(entry.path)
                            except OSError:
                                pass
        except OSError:
            pass

    _recurse(dir_path, max_depth)
    return found


def detect_config_files(expanded_paths: List[str]) -> List[str]:
    """Return local config file paths that actually exist on this machine.

    Parameters
    ----------
    expanded_paths:
        List of expanded filesystem paths obtained from PCGamingWiki (e.g. via
        :meth:`PCGamingWikiClient.get_config_paths`).

    Returns
    -------
    list[str]
        Absolute paths of config files that exist locally.  Directory paths are
        scanned recursively up to :data:`_DIR_SCAN_DEPTH` levels deep.  Steam
        userdata paths are always excluded.
    """
    found: List[str] = []
    for path in expanded_paths:
        if _is_expanded_registry_path(path):
            # Registry paths are always "found" – actual reading happens at export time
            found.append(path)
        elif os.path.isdir(path):
            found.extend(_scan_directory(path))
        elif os.path.isfile(path):
            found.append(path)
    return found


class ConfigExporter:
    """Export game configs enriched with PCGamingWiki path metadata.

    The output JSON package has the following structure::

        {
            "version": 2,
            "games": {
                "<game_name>": {
                    "detected_install_path": "<path>",
                    "platform": "<platform>",
                    "pcgamingwiki": {
                        "page_title": "<title>",
                        "url": "<url>",
                        "raw_paths": ["<raw_path>", ...],
                        "expanded_paths": ["<expanded_path>", ...],
                        "error": null
                    },
                    "config_files": [
                        {
                            "expanded_path": "<path>",
                            "found": true,
                            "content": "<text>",
                            "truncated": false,
                            "error": null
                        },
                        ...
                    ]
                },
                ...
            }
        }

    If no *wiki_client* is provided, ``pcgamingwiki`` and ``config_files``
    fields will be ``null`` / empty in the output.
    """

    FORMAT_VERSION = 2

    def __init__(self, wiki_client: Optional[Any] = None) -> None:
        self._wiki = wiki_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export(self, games: List[Any], output_path: str) -> None:
        """Export game configuration info to *output_path*.

        Parameters
        ----------
        games:
            Iterable of game objects.  Each object must expose at least a
            ``.name`` attribute and optionally ``.install_path`` and
            ``.platform``.
        output_path:
            Destination path for the generated JSON package (e.g.
            ``backup.json``).
        """
        package: Dict[str, Any] = {
            "version": self.FORMAT_VERSION,
            "games": {},
        }

        for game in games:
            game_name = getattr(game, "name", str(game))
            package["games"][game_name] = self._build_game_info(game)

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(package, fh, indent=2, ensure_ascii=False)

    def _build_game_info(self, game: Any) -> Dict[str, Any]:
        """Build the full info dict for a single game object."""
        info: Dict[str, Any] = {
            "detected_install_path": getattr(game, "install_path", ""),
            "platform": getattr(game, "platform", ""),
            "pcgamingwiki": None,
            "config_files": [],
        }

        if self._wiki is not None:
            game_name = getattr(game, "name", str(game))
            wiki_result = self._query_wiki(game_name)
            info["pcgamingwiki"] = wiki_result
            expanded_paths: List[str] = wiki_result.get("expanded_paths") or []
            config_files: List[Dict[str, Any]] = []
            for path in expanded_paths:
                if _is_expanded_registry_path(path):
                    config_files.append(_read_registry_key(path))
                elif os.path.isdir(path):
                    # Wiki returned a folder path – scan for config files
                    for file_path in _scan_directory(path):
                        config_files.append(_try_read_file(file_path))
                else:
                    config_files.append(_try_read_file(path))
            info["config_files"] = config_files

        return info

    def _query_wiki(self, game_name: str) -> Dict[str, Any]:
        """Query the wiki client and return a structured result dict."""
        result: Dict[str, Any] = {
            "page_title": game_name,
            "url": f"https://www.pcgamingwiki.com/wiki/{game_name.replace(' ', '_')}",
            "raw_paths": [],
            "expanded_paths": [],
            "error": None,
        }
        try:
            wiki_info = self._wiki.get_config_info(game_name)
            result["raw_paths"] = wiki_info.get("raw_paths") or []
            result["expanded_paths"] = wiki_info.get("expanded_paths") or []
            result["error"] = wiki_info.get("error")
        except Exception as exc:
            result["error"] = str(exc)
        return result
