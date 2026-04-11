"""Config path diagnostic tool.

Usage:
    python tools/diagnose_config.py "Game Name"

For each PCGamingWiki path this tool reports:
  - Raw path as returned by the Wiki
  - Expanded (absolute) path on this machine
  - Whether the file exists
  - Whether the PARENT directory exists
  → If parent exists but file doesn't: config not yet generated (run the game first)
  → If parent doesn't exist:           path is wrong or game isn't installed there
  - If parent is a directory: lists config-like files found inside it
"""

from __future__ import annotations

import os
import sys

# Allow running from project root or tools/ subdirectory
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from wiki_api import PCGamingWikiClient
from wiki_api.pcgamingwiki import _expand_path_tokens

_CONFIG_EXTENSIONS = frozenset({".ini", ".cfg", ".config", ".json", ".xml", ".txt"})

# ANSI colours (work on Windows 10+ terminals)
_GREEN  = "\033[92m"
_YELLOW = "\033[93m"
_RED    = "\033[91m"
_CYAN   = "\033[96m"
_RESET  = "\033[0m"
_BOLD   = "\033[1m"


def _colour(text: str, code: str) -> str:
    return f"{code}{text}{_RESET}"


def _scan_dir_for_configs(directory: str, max_depth: int = 2) -> list[str]:
    found: list[str] = []

    def _walk(path: str, depth: int) -> None:
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False) and depth > 0:
                        _walk(entry.path, depth - 1)
                    elif entry.is_file(follow_symlinks=False):
                        if os.path.splitext(entry.name)[1].lower() in _CONFIG_EXTENSIONS:
                            found.append(entry.path)
        except OSError:
            pass

    _walk(directory, max_depth)
    return found


def _classify_expanded_path(expanded: str) -> tuple[str, list[str]]:
    """Classify one expanded path.

    Returns a tuple ``(status, matches)`` where status is one of:
    ``found`` | ``not_generated`` | ``wrong_path``.
    """
    if os.path.isfile(expanded):
        return ("found", [expanded])

    if os.path.isdir(expanded):
        matches = _scan_dir_for_configs(expanded, max_depth=1)
        if matches:
            return ("found", matches)
        return ("not_generated", [])

    parent = os.path.dirname(expanded)
    if os.path.isdir(parent):
        return ("not_generated", _scan_dir_for_configs(parent, max_depth=1))
    return ("wrong_path", [])


def diagnose(game_name: str) -> None:
    print(f"\n{_colour('=' * 60, _BOLD)}")
    print(f"  Diagnosing: {_colour(game_name, _CYAN)}")
    print(f"{_colour('=' * 60, _BOLD)}\n")

    client = PCGamingWikiClient()
    info = client.get_config_info(game_name)

    wiki_url = info.get("url", "N/A")
    print(f"PCGamingWiki page : {wiki_url}")

    if info.get("error"):
        print(_colour(f"\n[ERROR] Wiki lookup failed: {info['error']}", _RED))
        print("  → This may be a network issue or the game has no Wiki page.")
        return

    raw_paths: list[str] = info.get("raw_paths", [])
    expanded_paths: list[str] = info.get("expanded_paths", [])

    if not raw_paths:
        print(_colour("\n[WARN] No config paths found on PCGamingWiki for this game.", _YELLOW))
        print("  → The game may not have a Wiki entry, or paths are not documented.")
        return

    print(f"\nFound {len(raw_paths)} path(s) from Wiki ({len(expanded_paths)} non-registry):\n")

    for i, raw in enumerate(raw_paths, 1):
        expanded = expanded_paths[i - 1] if i <= len(expanded_paths) else _expand_path_tokens(raw)
        status, matches = _classify_expanded_path(expanded)
        parent = os.path.dirname(expanded)

        print(f"  [{i}] Raw     : {raw}")
        print(f"       Expanded: {expanded}")

        if status == "found":
            print(f"       Status  : {_colour('FILE EXISTS ✓', _GREEN)}")
            if len(matches) > 1:
                print("       Detected config-like files:")
                for f in matches:
                    print(f"         • {f}")
        elif status == "not_generated":
            print(f"       Status  : {_colour('Parent dir exists, file NOT found', _YELLOW)}")
            print(f"       {_colour('→ Config not yet generated — run the game once to create it.', _YELLOW)}")
            if matches:
                print(f"       Files in parent dir:")
                for f in matches:
                    print(f"         • {f}")
            else:
                print(f"       (No config-like files found in parent directory)")
        else:
            print(f"       Status  : {_colour('Parent dir does NOT exist', _RED)}")
            # Walk up until we find an ancestor that exists
            ancestor = parent
            depth = 0
            while ancestor and not os.path.isdir(ancestor) and depth < 8:
                ancestor = os.path.dirname(ancestor)
                depth += 1
            if ancestor and os.path.isdir(ancestor):
                print(f"       {_colour(f'→ Nearest existing ancestor: {ancestor}', _RED)}")
                print(f"       {_colour('→ Likely a wrong path OR game is not installed in the expected location.', _RED)}")
            else:
                print(f"       {_colour('→ Could not find any matching ancestor directory.', _RED)}")

        print()

    print(_colour('-' * 60, _BOLD))
    print("Summary:")
    statuses = [_classify_expanded_path(p)[0] for p in expanded_paths]
    exists_count = sum(1 for s in statuses if s == "found")
    missing_parent = sum(1 for s in statuses if s == "wrong_path")
    parent_ok_file_missing = sum(1 for s in statuses if s == "not_generated")
    print(f"  Files found      : {_colour(str(exists_count), _GREEN)}")
    print(f"  Parent OK, no file (run game): {_colour(str(parent_ok_file_missing), _YELLOW)}")
    print(f"  Parent missing (wrong path)  : {_colour(str(missing_parent), _RED)}")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/diagnose_config.py \"Game Name\"")
        sys.exit(1)
    diagnose(" ".join(sys.argv[1:]))
