"""PCGamingWiki API client.

Uses the MediaWiki API exposed by PCGamingWiki to look up the configuration
file paths for a given game title.
"""

from __future__ import annotations

import glob as _glob_module
import re
import os
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

try:
    from bs4 import BeautifulSoup  # type: ignore
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore

# PCGamingWiki Cargo API endpoint
_API_URL = "https://www.pcgamingwiki.com/w/api.php"
_WIKI_BASE = "https://www.pcgamingwiki.com/wiki/"

# Map common path tokens to OS-specific directories
_PATH_TOKENS: dict = {
    "%USERPROFILE%": os.path.expanduser("~"),
    "%APPDATA%": os.environ.get("APPDATA", os.path.expanduser("~/.config")),
    "%LOCALAPPDATA%": os.environ.get("LOCALAPPDATA", os.path.expanduser("~/.local/share")),
    "%PUBLIC%": os.environ.get("PUBLIC", os.path.expanduser("~")),
    "$HOME": os.path.expanduser("~"),
    "$XDG_CONFIG_HOME": os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "$XDG_DATA_HOME": os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
}


def _get_documents_path() -> str:
    """Return the real My Documents folder path, respecting OneDrive redirection.

    On Windows, My Documents may be redirected to OneDrive (e.g.
    ``C:\\Users\\<user>\\OneDrive\\文件``).  Reading the path via the
    Windows Shell API (``SHGetFolderPath`` / ``SHGetKnownFolderPath``) always
    returns the current effective location.

    Falls back to ``~/Documents`` on non-Windows or if the API is unavailable.
    """
    if os.name == "nt":
        try:
            import ctypes
            import ctypes.wintypes

            # CSIDL_PERSONAL = 0x0005 → My Documents
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, 0x0005, None, 0, buf)
            path = buf.value
            if path and os.path.isdir(path):
                return path
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def _get_steam_path() -> str:
    """Return the Steam installation path from the Windows registry, or ``""``."""
    if os.name != "nt":
        return ""
    try:
        import winreg  # type: ignore

        candidates = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam", "SteamPath"),
        ]
        for hive, key_path, value_name in candidates:
            try:
                with winreg.OpenKey(hive, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, value_name)
                    if value:
                        # SteamPath may use forward slashes; normalise to OS separator
                        return os.path.normpath(value)
            except (FileNotFoundError, OSError):
                continue
    except ImportError:
        pass
    return ""


# Map PCGamingWiki template tags to OS-specific paths.
# NOTE: All keys use the canonical upper-case P form ({{P|…}}).  The expansion
# function normalises lower-case {{p|…}} occurrences before lookup.
_WIKI_TAG_MAP: dict = {
    "{{P|userprofile}}": os.path.expanduser("~"),
    "{{P|userappdata}}": os.environ.get("APPDATA", os.path.expanduser("~/.config")),
    "{{P|appdata}}": os.environ.get("APPDATA", os.path.expanduser("~/.config")),
    "{{P|localappdata}}": os.environ.get("LOCALAPPDATA", os.path.expanduser("~/.local/share")),
    "{{P|programdata}}": os.environ.get("PROGRAMDATA", "/usr/share"),
    "{{P|documents}}": _get_documents_path(),
    "{{P|uid}}": "*",  # Represents SteamID3; expanded to glob wildcard
    "{{P|game}}": "",  # Represents the game folder name
    "{{P|osxhome}}": os.path.expanduser("~"),
    "{{P|linuxhome}}": os.path.expanduser("~"),
    "{{P|xdgconfig}}": os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "{{P|xdgdata}}": os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
    "{{P|steam}}": _get_steam_path(),
    # Compound tokens: some Wiki pages write {{P|base/subdir}} as a shorthand.
    "{{P|userprofile/documents}}": _get_documents_path(),
    "{{P|userprofile/appdata}}": os.environ.get("APPDATA", os.path.expanduser("~/.config")),
    "{{P|userprofile/localappdata}}": os.environ.get("LOCALAPPDATA", os.path.expanduser("~/.local/share")),
}

# Registry path token prefixes – these are not filesystem paths
_REGISTRY_TOKENS: tuple = ("{{p|hkcu}}", "{{p|hklm}}", "{{p|hkcr}}", "{{p|hku}}", "{{p|hkcc}}")


def _remove_duplicate_path_segments(path: str) -> str:
    """Remove consecutive duplicate segments from *path*.

    For example ``C:\\AppData\\Roaming\\Roaming\\App`` becomes
    ``C:\\AppData\\Roaming\\App``.  This fixes paths where a token such as
    ``{{P|appdata}}`` (which already includes the ``Roaming`` directory on
    Windows) is followed by a redundant ``\\Roaming\\`` suffix.
    """
    sep = os.sep
    # Normalise all slashes to the OS separator before splitting
    normalised = path.replace("/", sep)
    # Preserve a leading separator (UNC paths, Unix absolute paths)
    leading = normalised[: len(normalised) - len(normalised.lstrip(sep))]
    parts = normalised.split(sep)
    deduped: List[str] = []
    for part in parts:
        if deduped and part and part == deduped[-1]:
            continue  # skip consecutive duplicate segment
        deduped.append(part)
    return leading + sep.join(p for p in deduped if p)


def _resolve_uid_glob(path: str) -> Optional[str]:
    """Resolve a wildcard *path* produced by ``{{p|uid}}`` expansion.

    If *path* contains no ``*`` it is returned unchanged.  Otherwise
    :func:`glob.glob` is used to find matching filesystem entries and the
    one with the most recent modification time is returned.  Returns
    ``None`` when the glob matches nothing.
    """
    if "*" not in path:
        return path
    matches = _glob_module.glob(path)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    try:
        return max(matches, key=os.path.getmtime)
    except OSError:
        return matches[0]


def _expand_path_tokens(path: str) -> str:
    """Expand PCGamingWiki path tokens and Wiki template tags to absolute OS paths.

    Processing order:

    1. Normalise ``{{p|…}}`` (lower-case *p*) to canonical ``{{P|…}}`` form.
    2. Expand Wiki template tags from :data:`_WIKI_TAG_MAP`.
    3. Expand standard Windows environment variables via
       :func:`os.path.expandvars`.
    4. Expand remaining special tokens defined in :data:`_PATH_TOKENS`.
    5. Normalise the result with :func:`os.path.normpath`.
    6. Remove consecutive duplicate path segments (fixes double-``Roaming``
       that arises when a token already includes ``Roaming`` and the raw path
       appends ``\\Roaming\\`` again).
    7. Convert separators to ``/`` so output is stable across platforms.
    """
    # 1. Normalise {{p|...}} or {{P|...}} → {{P|<lowercase content with / sep>}}
    #    so tag lookups in _WIKI_TAG_MAP are case-insensitive and separator-agnostic.
    #    This handles both {{P|userprofile/Documents}} and {{p|userprofile\Documents}}.
    path = re.sub(
        r"\{\{[Pp]\|([^{}]+)\}\}",
        lambda m: "{{P|" + m.group(1).lower().replace("\\", "/") + "}}",
        path,
    )

    # 2. Expand Wiki template tags
    for tag, replacement in _WIKI_TAG_MAP.items():
        path = path.replace(tag, replacement)

    # 3. Expand standard Windows environment variables (e.g. %APPDATA%)
    path = os.path.expandvars(path)

    # 4. Expand remaining special tokens
    for token, replacement in _PATH_TOKENS.items():
        path = path.replace(token, replacement)

    # 5. Normalise slashes/dots
    path = os.path.normpath(path)

    # 6. Remove consecutive duplicate segments (e.g. Roaming\Roaming)
    path = _remove_duplicate_path_segments(path)

    # 7. Use forward slashes for deterministic cross-platform output.
    path = path.replace("\\", "/")

    return path


def _is_registry_path(path: str) -> bool:
    """Return ``True`` if *path* is a Windows registry path, not a filesystem path."""
    path_lower = path.lower()
    return any(path_lower.startswith(tok) for tok in _REGISTRY_TOKENS)


def _find_template_blocks(wikitext: str, template_name: str) -> List[str]:
    """Return all ``{{template_name|…}}`` blocks from *wikitext*, handling nesting.

    Uses brace-counting so nested ``{{P|…}}`` tokens inside a block are not
    mistaken for the closing ``}}`` of the outer template.
    """
    blocks: List[str] = []
    search_lower = ("{{" + template_name).lower()
    wt_lower = wikitext.lower()
    pos = 0
    while True:
        idx = wt_lower.find(search_lower, pos)
        if idx == -1:
            break
        # Verify the match is followed by '|' or '}}' (i.e. it's the full name)
        after = idx + len(search_lower)
        if after >= len(wikitext) or wikitext[after] not in ("|", "}"):
            pos = idx + 1
            continue
        # Walk forward counting '{{' / '}}' to find the matching close
        depth = 0
        i = idx
        while i < len(wikitext):
            if wikitext[i : i + 2] == "{{":
                depth += 1
                i += 2
            elif wikitext[i : i + 2] == "}}":
                depth -= 1
                i += 2
                if depth == 0:
                    break
            else:
                i += 1
        blocks.append(wikitext[idx:i])
        pos = i
    return blocks


def _split_by_pipe(content: str) -> List[str]:
    """Split *content* on ``|`` while respecting ``{{…}}`` nesting."""
    parts: List[str] = []
    depth = 0
    buf: List[str] = []
    i = 0
    while i < len(content):
        if content[i : i + 2] == "{{":
            depth += 1
            buf.append("{{")
            i += 2
        elif content[i : i + 2] == "}}":
            depth -= 1
            buf.append("}}")
            i += 2
        elif content[i] == "|" and depth == 0:
            parts.append("".join(buf))
            buf = []
            i += 1
        else:
            buf.append(content[i])
            i += 1
    if buf:
        parts.append("".join(buf))
    return parts


def _parse_gamedata_config(
    wikitext: str, os_filter: str = "Windows"
) -> Tuple[List[str], List[str]]:
    """Parse ``{{Game data/config|OS|path|…}}`` blocks from *wikitext*.

    Parameters
    ----------
    wikitext:
        Raw wikitext fetched from PCGamingWiki.
    os_filter:
        Only extract paths from blocks whose OS argument contains this string
        (case-insensitive).  Defaults to ``"Windows"``.

    Returns
    -------
    tuple[list[str], list[str]]
        ``(raw_paths, expanded_paths)``.  Registry paths (``{{P|hkcu}}`` etc.)
        are included in *raw_paths* for diagnostics but excluded from
        *expanded_paths*.
    """
    raw_paths: List[str] = []
    expanded_paths: List[str] = []
    for block in _find_template_blocks(wikitext, "Game data/config"):
        # Strip outer {{ and }} then split on | (respecting nested templates)
        if not (block.startswith("{{") and block.endswith("}}")):
            continue  # guard against malformed blocks
        inner = block[2:-2]
        parts = _split_by_pipe(inner)
        # parts[0] == "Game data/config", parts[1] == OS, parts[2:] == paths
        if len(parts) < 3:
            continue
        os_name = parts[1].strip()
        if os_filter.lower() not in os_name.lower():
            continue
        for raw in parts[2:]:
            raw = raw.strip()
            if not raw:
                continue
            raw_paths.append(raw)
            if not _is_registry_path(raw):
                expanded = _expand_path_tokens(raw)
                resolved = _resolve_uid_glob(expanded)
                if resolved is not None:
                    expanded_paths.append(resolved)
    return raw_paths, expanded_paths


class PCGamingWikiClient:
    """Client for querying PCGamingWiki for game configuration paths."""

    def __init__(self, timeout: int = 10) -> None:
        self.timeout = timeout
        self._session = requests.Session() if requests else None
        if self._session:
            self._session.headers.update(
                {"User-Agent": "GameSettingAligner/1.0 (https://github.com/ElyZeng/Game-setting-aligner)"}
            )

    def search_game(self, title: str) -> Optional[str]:
        """Return the PCGamingWiki page title for the given game, or None."""
        if self._session is None:
            return None

        params = {
            "action": "opensearch",
            "search": title,
            "limit": 1,
            "format": "json",
        }
        try:
            response = self._session.get(_API_URL, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            if data and len(data) > 1 and data[1]:
                return data[1][0]
        except Exception:
            pass
        return None

    def get_config_paths(self, game_title: str) -> List[str]:
        """Return a list of expanded config file paths for the given game title.

        Uses the PCGamingWiki Cargo API to query the ``Config_game_data`` table.
        Falls back to the MediaWiki API (wikitext parsing) and then to HTML
        scraping if the Cargo query returns no results.
        """
        _, expanded = self._query_cargo_raw(game_title)
        if not expanded:
            _, expanded = self._query_mediawiki_raw(game_title)
        if not expanded:
            _, expanded = self._scrape_wiki_page_raw(game_title)
        return expanded

    def get_config_info(self, game_title: str) -> Dict[str, Any]:
        """Return a dict with raw and expanded config paths for *game_title*.

        The returned dict has the following keys:

        ``page_title``
            The game title as queried.
        ``url``
            The expected PCGamingWiki URL for this game.
        ``raw_paths``
            List of raw path strings as returned by PCGamingWiki (may contain
            template tags such as ``{{P|userprofile}}``).
        ``expanded_paths``
            List of path strings after expanding tokens to local OS paths.
            Registry paths (e.g. ``{{P|hkcu}}\\…``) are omitted here but are
            present in ``raw_paths`` for diagnostics.
        ``error``
            ``None`` on success, or an error message string on failure.
        """
        result: Dict[str, Any] = {
            "page_title": game_title,
            "url": _WIKI_BASE + game_title.replace(" ", "_"),
            "raw_paths": [],
            "expanded_paths": [],
            "error": None,
        }
        if self._session is None:
            result["error"] = "requests library not available"
            return result
        try:
            raw, expanded = self._query_cargo_raw(game_title)
            if not raw:
                raw, expanded = self._query_mediawiki_raw(game_title)
            if not raw:
                raw, expanded = self._scrape_wiki_page_raw(game_title)
            result["raw_paths"] = raw
            result["expanded_paths"] = expanded
        except Exception as exc:  # pragma: no cover
            result["error"] = str(exc)
        return result

    def _query_cargo_raw(self, game_title: str) -> Tuple[List[str], List[str]]:
        """Query PCGamingWiki Cargo tables for config paths.

        Returns a tuple ``(raw_paths, expanded_paths)``.
        """
        if self._session is None:
            return [], []

        # Escape single quotes to avoid injection into the Cargo WHERE clause.
        safe_title = game_title.replace("'", "\\'")
        params = {
            "action": "cargoquery",
            "tables": "Config_game_data",
            "fields": "Path,OS",
            "where": f"Holds='Game data' AND _pageName='{safe_title}'",
            "format": "json",
            "limit": 20,
        }
        try:
            response = self._session.get(_API_URL, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            results = data.get("cargoquery", [])
            raw_paths: List[str] = []
            expanded_paths: List[str] = []
            for result in results:
                raw_path = result.get("title", {}).get("Path", "")
                if raw_path:
                    raw_paths.append(raw_path)
                    if not _is_registry_path(raw_path):
                        expanded = _expand_path_tokens(raw_path)
                        resolved = _resolve_uid_glob(expanded)
                        if resolved is not None:
                            expanded_paths.append(resolved)
            return raw_paths, expanded_paths
        except Exception:
            return [], []

    def _query_mediawiki_raw(self, game_title: str) -> Tuple[List[str], List[str]]:
        """Fetch wikitext via the MediaWiki API and parse config paths.

        Uses ``action=query&prop=revisions`` to retrieve the raw wikitext for
        *game_title* and then calls :func:`_parse_gamedata_config` to extract
        paths from ``{{Game data/config|Windows|…}}`` blocks.

        This method is used as a fallback when :meth:`_query_cargo_raw` returns
        no results.

        Returns a tuple ``(raw_paths, expanded_paths)``.
        """
        if self._session is None:
            return [], []

        params = {
            "action": "query",
            "prop": "revisions",
            "rvslots": "main",
            "rvprop": "content",
            "titles": game_title,
            "format": "json",
        }
        try:
            response = self._session.get(_API_URL, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            pages = data.get("query", {}).get("pages", {})
            if not pages:
                return [], []
            page = next(iter(pages.values()))
            revisions = page.get("revisions")
            if not revisions:
                return [], []
            slot = revisions[0].get("slots", {}).get("main", {})
            wikitext = slot.get("*", "")
            if not wikitext:
                return [], []
            return _parse_gamedata_config(wikitext)
        except Exception:
            return [], []

    def _scrape_wiki_page_raw(self, game_title: str) -> Tuple[List[str], List[str]]:
        """Scrape the PCGamingWiki page for config paths as a fallback.

        Returns a tuple ``(raw_paths, expanded_paths)``.
        """
        if self._session is None or BeautifulSoup is None:
            return [], []

        url = _WIKI_BASE + game_title.replace(" ", "_")
        try:
            response = self._session.get(url, timeout=self.timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception:
            return [], []

        raw_paths: List[str] = []
        expanded_paths: List[str] = []
        # Config table rows typically contain path-like text with slashes or backslashes
        for td in soup.find_all("td", class_=re.compile(r"game-data", re.I)):
            text = td.get_text(separator=" ", strip=True)
            if re.search(r"[/\\]", text):
                raw_paths.append(text)
                expanded_paths.append(_expand_path_tokens(text))

        return raw_paths, expanded_paths
