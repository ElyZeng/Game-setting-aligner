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
    "{{P|userappdata}}": os.environ.get("APPDATA", os.path.expanduser("~/.config")),
    "{{P|appdata}}": os.environ.get("APPDATA", os.path.expanduser("~/.config")),
    "{{P|localappdata}}": os.environ.get("LOCALAPPDATA", os.path.expanduser("~/.local/share")),
    "{{P|programdata}}": os.environ.get("PROGRAMDATA", "/usr/share"),
    "{{P|documents}}": os.path.join(os.path.expanduser("~"), "Documents"),
    "{{P|uid}}": "*",  # Typically represents SteamID3; use wildcard
    "{{P|game}}": "",  # Represents the game folder name
    "{{P|osxhome}}": os.path.expanduser("~"),
    "{{P|linuxhome}}": os.path.expanduser("~"),
    "{{P|xdgconfig}}": os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "{{P|xdgdata}}": os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
    "{{P|steam}}": "",
}

# Registry path token prefixes – these are not filesystem paths
_REGISTRY_TOKENS: tuple = ("{{p|hkcu}}", "{{p|hklm}}", "{{p|hkcr}}", "{{p|hku}}", "{{p|hkcc}}")


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
                expanded_paths.append(_expand_path_tokens(raw))
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
                    expanded_paths.append(_expand_path_tokens(raw_path))
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
