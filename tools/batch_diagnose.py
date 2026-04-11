"""Batch config path diagnostic: scans all installed games and categorises results.

Usage:
    python tools/batch_diagnose.py

Output:
    Three categories per game:
      ✅ Config found
      ⚠️  Parent dir exists but file missing (run the game once)
      ❌  Parent dir missing (wrong path or not installed here)
      ❓  No Wiki entry / error
"""

from __future__ import annotations

import os
import sys
import concurrent.futures

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scanner import SteamScanner, EpicScanner, GOGScanner
from wiki_api import PCGamingWikiClient

_REGISTRY_TOKENS = ("{{p|hkcu}}", "{{p|hklm}}", "{{p|hkcr}}", "{{p|hku}}", "{{p|hkcc}}")
_CONFIG_EXTENSIONS = frozenset({".ini", ".cfg", ".config", ".json", ".xml", ".txt"})

FOUND        = "found"
NOT_GENERATED = "not_generated"   # parent exists, file doesn't
WRONG_PATH   = "wrong_path"       # parent doesn't exist
NO_WIKI      = "no_wiki"          # no info / error


def _is_registry(path: str) -> bool:
    lower = path.lower()
    return any(lower.startswith(t) for t in _REGISTRY_TOKENS)


def _scan_dir_for_configs(directory: str, max_depth: int = 1) -> list[str]:
    found: list[str] = []

    def _walk(path: str, depth: int) -> None:
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False) and depth > 0:
                        _walk(entry.path, depth - 1)
                    elif entry.is_file(follow_symlinks=False):
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in _CONFIG_EXTENSIONS:
                            found.append(entry.path)
        except OSError:
            pass

    _walk(directory, max_depth)
    return found


def _classify_path(expanded: str):
    """Return (FOUND | NOT_GENERATED | WRONG_PATH) for one expanded path."""
    if os.path.isfile(expanded):
        return FOUND

    if os.path.isdir(expanded):
        if _scan_dir_for_configs(expanded, max_depth=1):
            return FOUND
        return NOT_GENERATED

    parent = os.path.dirname(expanded)
    if os.path.isdir(parent):
        return NOT_GENERATED
    return WRONG_PATH


def _diagnose_game(game) -> dict:
    client = PCGamingWikiClient()
    name = getattr(game, "name", str(game))
    platform = getattr(game, "platform", "?")

    try:
        info = client.get_config_info(name)
    except Exception as exc:
        return {"name": name, "platform": platform, "status": NO_WIKI, "reason": str(exc), "details": []}

    if info.get("error") or not info.get("raw_paths"):
        return {"name": name, "platform": platform, "status": NO_WIKI,
                "reason": info.get("error") or "no paths on wiki", "details": []}

    expanded_paths = [p for p in info.get("expanded_paths", []) if not _is_registry(p)]
    raw_paths      = info.get("raw_paths", [])

    if not expanded_paths:
        return {"name": name, "platform": platform, "status": NO_WIKI,
                "reason": "only registry paths", "details": []}

    details = []
    for exp in expanded_paths:
        details.append({"path": exp, "status": _classify_path(exp)})

    # Overall status = worst case: wrong_path > not_generated > found
    statuses = {d["status"] for d in details}
    if WRONG_PATH in statuses:
        overall = WRONG_PATH
    elif NOT_GENERATED in statuses:
        overall = NOT_GENERATED
    else:
        overall = FOUND

    return {"name": name, "platform": platform, "status": overall, "details": details}


def main() -> None:
    # 1. Collect all installed games
    games = []
    for scanner in (SteamScanner(), EpicScanner(), GOGScanner()):
        try:
            games.extend(scanner.scan())
        except Exception:
            pass

    print(f"Found {len(games)} installed game(s). Querying PCGamingWiki in parallel…\n")

    # 2. Diagnose in parallel (max 8 threads to be polite to the API)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_diagnose_game, g): g for g in games}
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            done += 1
            result = fut.result()
            results.append(result)
            sys.stdout.write(f"\r  Progress: {done}/{len(games)}   ")
            sys.stdout.flush()

    print("\n")

    # 3. Bucket and sort
    buckets = {FOUND: [], NOT_GENERATED: [], WRONG_PATH: [], NO_WIKI: []}
    for r in results:
        buckets[r["status"]].append(r)

    for bucket in buckets.values():
        bucket.sort(key=lambda x: x["name"].lower())

    # 4. Print report
    sep = "─" * 64

    # ── Found ────────────────────────────────────────────────────
    print(f"✅  CONFIG FOUND  ({len(buckets[FOUND])} games)")
    print(sep)
    for r in buckets[FOUND]:
        print(f"  {r['name']}  [{r['platform']}]")
        for d in r["details"]:
            if d["status"] == FOUND:
                short = d["path"]
                print(f"    • {short}")
    print()

    # ── Not generated ────────────────────────────────────────────
    print(f"⚠️   CONFIG NOT YET GENERATED  ({len(buckets[NOT_GENERATED])} games)")
    print("  (Parent directory exists but config file hasn't been created — run the game once)")
    print(sep)
    for r in buckets[NOT_GENERATED]:
        print(f"  {r['name']}  [{r['platform']}]")
        for d in r["details"]:
            marker = "✅" if d["status"] == FOUND else "⚠️ "
            print(f"    {marker} {d['path']}")
    print()

    # ── Wrong path ───────────────────────────────────────────────
    print(f"❌  PATH NOT FOUND  ({len(buckets[WRONG_PATH])} games)")
    print("  (Parent directory does not exist; path may be wrong or game not installed here)")
    print(sep)
    for r in buckets[WRONG_PATH]:
        print(f"  {r['name']}  [{r['platform']}]")
        for d in r["details"]:
            marker = "✅" if d["status"] == FOUND else ("⚠️ " if d["status"] == NOT_GENERATED else "❌")
            print(f"    {marker} {d['path']}")
    print()

    # ── No Wiki entry ────────────────────────────────────────────
    print(f"❓  NO WIKI ENTRY / LOOKUP FAILED  ({len(buckets[NO_WIKI])} games)")
    print(sep)
    for r in buckets[NO_WIKI]:
        print(f"  {r['name']}  [{r['platform']}]  — {r.get('reason', '')}")
    print()

    print(sep)
    print(f"Summary: ✅ {len(buckets[FOUND])}  ⚠️  {len(buckets[NOT_GENERATED])}  ❌ {len(buckets[WRONG_PATH])}  ❓ {len(buckets[NO_WIKI])}")


if __name__ == "__main__":
    main()
