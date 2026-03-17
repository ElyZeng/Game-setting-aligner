"""PCGamingWiki API client.

Uses the MediaWiki API exposed by PCGamingWiki to look up the configuration
file paths for a given game title.
"""

from __future__ import annotations

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

# Map PCGamingWiki template tags to OS-specific paths
_WIKI_TAG_MAP: dict = {
    "{{P|userprofile}}": os.path.expanduser("~"),
    "{{P|userappdata}}": os.environ.get("APPDATA", ""),
    "{{P|localappdata}}": os.environ.get("LOCALAPPDATA", ""),
    "{{P|uid}}": "*",  # Typically represents SteamID3; use wildcard
    "{{P|game}}": "",  # Represents the game folder name
}


def _expand_path_tokens(path: str) -> str:
    """Expand PCGamingWiki path tokens and Wiki template tags to absolute OS paths.

    Processing order:
    1. Wiki template tags (e.g. ``{{P|userprofile}}``)
    2. Standard Windows environment variables via :func:`os.path.expandvars`
    3. Remaining special tokens defined in :data:`_PATH_TOKENS`

    The result is normalised with :func:`os.path.normpath` to unify slash
direction across platforms.
    """
    # 1. Expand Wiki template tags
    for tag, replacement in _WIKI_TAG_MAP.items():
        path = path.replace(tag, replacement)

    # 2. Expand standard Windows environment variables (e.g. %APPDATA%)
    path = os.path.expandvars(path)

    # 3. Expand remaining special tokens
    for token, replacement in _PATH_TOKENS.items():
        path = path.replace(token, replacement)

    return os.path.normpath(path)


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
        Falls back to HTML scraping if the Cargo query returns no results.
        """
        _, expanded = self._query_cargo_raw(game_title)
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
                    expanded_paths.append(_expand_path_tokens(raw_path))
            return raw_paths, expanded_paths
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
