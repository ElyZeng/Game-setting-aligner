"""Main application GUI.

A modern dark-themed GUI built with CustomTkinter that lists detected games
with checkboxes and provides Export/Import functionality.
"""

from __future__ import annotations

import concurrent.futures
import os
import threading
from tkinter import filedialog, messagebox
from typing import Any, Dict, List, Optional

try:
    import customtkinter as ctk  # type: ignore
except ImportError:  # pragma: no cover
    ctk = None  # type: ignore

from scanner import SteamScanner, EpicScanner, GOGScanner
from wiki_api import PCGamingWikiClient
from config_manager import ConfigPackage, ConfigExporter, detect_config_files


# Sentinel used by GameRow.update_config_status to indicate a failed wiki lookup.
_UNABLE_TO_CHECK = object()


def _require_ctk() -> None:
    if ctk is None:
        raise ImportError(
            "customtkinter is required to run the GUI. "
            "Install it with: pip install customtkinter"
        )


class GameRow:
    """A single row in the game list containing a checkbox and a label."""

    def __init__(
        self,
        parent: Any,
        game_name: str,
        platform: str,
        install_path: str = "",
        config_files: Optional[List[str]] = None,
    ) -> None:
        self.game_name = game_name
        self.platform = platform
        self.install_path = install_path

        self.var = ctk.BooleanVar(value=False)
        self.frame = ctk.CTkFrame(parent, corner_radius=6)
        self.frame.pack(fill="x", padx=6, pady=2)

        self.checkbox = ctk.CTkCheckBox(
            self.frame,
            text=f"{game_name}  [{platform}]",
            variable=self.var,
            font=ctk.CTkFont(size=13),
        )
        self.checkbox.pack(side="left", padx=8, pady=4)

        # Config status label (right-aligned)
        self._config_label = ctk.CTkLabel(
            self.frame,
            text="",
            font=ctk.CTkFont(size=11),
        )
        self._config_label.pack(side="right", padx=8, pady=4)

        self.update_config_status(config_files)

    def update_config_status(self, config_files: Any) -> None:
        """Update the config file status label.

        Parameters
        ----------
        config_files:
            ``None``               → still querying (shows "🔄 Checking…")
            ``_UNABLE_TO_CHECK``   → wiki lookup failed (shows "Unable to check")
            ``[]``                 → query done, no config files found locally
            ``[path, …]``          → query done, one or more config files found
        """
        if config_files is None:
            self._config_label.configure(text="🔄 Checking…", text_color="gray")
        elif config_files is _UNABLE_TO_CHECK:
            self._config_label.configure(text="Unable to check", text_color="gray")
        elif len(config_files) == 0:
            self._config_label.configure(
                text="⚠️ No config files found", text_color="#d4a017"
            )
        else:
            count = len(config_files)
            self._config_label.configure(
                text=f"✅ {count} config file(s) found",
                text_color="#48bb78",
            )

    @property
    def name(self) -> str:
        """Alias for ``game_name`` for compatibility with scanner game objects."""
        return self.game_name

    @property
    def selected(self) -> bool:
        return bool(self.var.get())


class App:
    """Main application window."""

    def __init__(self) -> None:
        _require_ctk()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("Game Setting Aligner")
        self.root.geometry("800x600")
        self.root.minsize(600, 400)

        self._game_rows: List[GameRow] = []
        self._wiki_client = PCGamingWikiClient()
        self._package = ConfigPackage()

        self._build_ui()
        self._scan_games()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Top bar
        top_bar = ctk.CTkFrame(self.root, corner_radius=0)
        top_bar.pack(fill="x", padx=0, pady=0)

        title_label = ctk.CTkLabel(
            top_bar,
            text="Game Setting Aligner",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        title_label.pack(side="left", padx=16, pady=12)

        self._scan_btn = ctk.CTkButton(
            top_bar,
            text="🔍  Refresh",
            width=110,
            command=self._scan_games,
        )
        self._scan_btn.pack(side="right", padx=8, pady=10)

        # Status label
        self._status_label = ctk.CTkLabel(
            self.root,
            text="Scanning for games…",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self._status_label.pack(anchor="w", padx=16, pady=(4, 0))

        # Progress bar (shown while loading)
        self._progress = ctk.CTkProgressBar(self.root, mode="indeterminate")
        self._progress.pack(fill="x", padx=16, pady=(4, 0))

        # Game list inside a scrollable frame
        list_container = ctk.CTkFrame(self.root, corner_radius=8)
        list_container.pack(fill="both", expand=True, padx=16, pady=8)

        self._scroll_frame = ctk.CTkScrollableFrame(
            list_container,
            label_text="Installed Games",
            label_font=ctk.CTkFont(size=14, weight="bold"),
        )
        self._scroll_frame.pack(fill="both", expand=True, padx=4, pady=4)

        # Bottom action bar
        action_bar = ctk.CTkFrame(self.root, corner_radius=0)
        action_bar.pack(fill="x", padx=0, pady=0)

        self._select_all_btn = ctk.CTkButton(
            action_bar,
            text="Select All",
            width=100,
            fg_color="gray30",
            hover_color="gray40",
            command=self._select_all,
        )
        self._select_all_btn.pack(side="left", padx=8, pady=8)

        self._deselect_all_btn = ctk.CTkButton(
            action_bar,
            text="Deselect All",
            width=100,
            fg_color="gray30",
            hover_color="gray40",
            command=self._deselect_all,
        )
        self._deselect_all_btn.pack(side="left", padx=4, pady=8)

        self._import_btn = ctk.CTkButton(
            action_bar,
            text="⬆  Import Config",
            width=150,
            fg_color="#2b6cb0",
            hover_color="#2c5282",
            command=self._import_config,
        )
        self._import_btn.pack(side="right", padx=8, pady=8)

        self._export_btn = ctk.CTkButton(
            action_bar,
            text="⬇  Export Selected",
            width=150,
            command=self._export_selected,
        )
        self._export_btn.pack(side="right", padx=4, pady=8)

    # ------------------------------------------------------------------
    # Game scanning
    # ------------------------------------------------------------------

    def _scan_games(self) -> None:
        """Scan for installed games in a background thread."""
        self._set_scanning(True)
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self) -> None:
        games = []
        for scanner in (SteamScanner(), EpicScanner(), GOGScanner()):
            try:
                games.extend(scanner.scan())
            except Exception:
                pass
        self.root.after(0, self._on_scan_done, games)

    def _on_scan_done(self, games: List[Any]) -> None:
        # Clear old rows
        for row in self._game_rows:
            row.frame.destroy()
        self._game_rows.clear()

        if not games:
            self._status_label.configure(text="No games found.")
        else:
            self._status_label.configure(
                text=f"{len(games)} game(s) found. Checking config files…"
            )

        for game in games:
            name = getattr(game, "name", str(game))
            platform = getattr(game, "platform", "Unknown")
            install_path = getattr(game, "install_path", "")
            # config_files=None shows "Checking…" until Phase 2 updates the row
            row = GameRow(self._scroll_frame, name, platform, install_path, config_files=None)
            self._game_rows.append(row)

        self._set_scanning(False)

        # Phase 2: background Wiki query + local config detection
        if games:
            self._start_config_detection(list(games))

    def _set_scanning(self, scanning: bool) -> None:
        if scanning:
            self._progress.pack(fill="x", padx=16, pady=(4, 0))
            self._progress.start()
            self._export_btn.configure(state="disabled")
            self._import_btn.configure(state="disabled")
            self._scan_btn.configure(state="disabled")
        else:
            self._progress.stop()
            self._progress.pack_forget()
            self._export_btn.configure(state="normal")
            self._import_btn.configure(state="normal")
            self._scan_btn.configure(state="normal")

    def _start_config_detection(self, games: List[Any]) -> None:
        """Start Phase-2 background config detection for all games.

        Uses a :class:`~concurrent.futures.ThreadPoolExecutor` with up to 5
        workers to query PCGamingWiki and check local config files in parallel.
        Each completed result is pushed back to the main thread via
        ``root.after(0, …)`` so that UI updates are always thread-safe.
        """
        # Build a mapping from game name to its GameRow so we can update the
        # correct row when a result arrives.
        rows_by_name: Dict[str, GameRow] = {
            row.game_name: row for row in self._game_rows
        }

        def _detect(game: Any):
            """Query Wiki and detect local config files for a single game."""
            game_name = getattr(game, "name", str(game))
            try:
                expanded_paths = self._wiki_client.get_config_paths(game_name)
                found_files = detect_config_files(expanded_paths)
            except Exception:
                # Graceful degradation: network errors, timeouts, parsing
                # failures, etc. should not crash the background thread.
                return game_name, _UNABLE_TO_CHECK
            return game_name, found_files

        def _run_all() -> None:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_game = {
                    executor.submit(_detect, game): game for game in games
                }
                for future in concurrent.futures.as_completed(future_to_game):
                    try:
                        game_name, result = future.result()
                    except Exception:
                        # Defensive catch: future.result() itself should not
                        # raise since _detect handles its own errors, but guard
                        # against any unexpected executor-level failures.
                        game = future_to_game[future]
                        game_name = getattr(game, "name", str(game))
                        result = _UNABLE_TO_CHECK

                    row = rows_by_name.get(game_name)
                    if row is not None:
                        self.root.after(0, row.update_config_status, result)

            # All done – update status bar back to a simple count
            self.root.after(
                0,
                self._status_label.configure,
                {"text": f"{len(self._game_rows)} game(s) found."},
            )

        threading.Thread(target=_run_all, daemon=True).start()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _select_all(self) -> None:
        for row in self._game_rows:
            row.var.set(True)

    def _deselect_all(self) -> None:
        for row in self._game_rows:
            row.var.set(False)

    def _export_selected(self) -> None:
        selected = [row for row in self._game_rows if row.selected]
        if not selected:
            messagebox.showwarning("No Games Selected", "Please select at least one game to export.")
            return

        output_path = filedialog.asksaveasfilename(
            title="Save Config Package",
            defaultextension=".json",
            filetypes=[("JSON Package", "*.json"), ("All Files", "*.*")],
        )
        if not output_path:
            return

        self._set_scanning(True)
        self._status_label.configure(text="Fetching config paths and exporting…")
        threading.Thread(
            target=self._do_export,
            args=(selected, output_path),
            daemon=True,
        ).start()

    def _do_export(self, rows: List[GameRow], output_path: str) -> None:
        exporter = ConfigExporter(wiki_client=self._wiki_client)
        try:
            exporter.export(rows, output_path)
            self.root.after(
                0,
                messagebox.showinfo,
                "Export Complete",
                f"Config package saved to:\n{output_path}",
            )
        except Exception as exc:
            self.root.after(
                0,
                messagebox.showerror,
                "Export Failed",
                str(exc),
            )
        finally:
            self.root.after(0, self._set_scanning, False)
            self.root.after(
                0,
                self._status_label.configure,
                {"text": f"{len(self._game_rows)} game(s) found."},
            )

    def _import_config(self) -> None:
        package_path = filedialog.askopenfilename(
            title="Open Config Package",
            filetypes=[("JSON Package", "*.json"), ("All Files", "*.*")],
        )
        if not package_path:
            return

        if not messagebox.askyesno(
            "Confirm Import",
            "This will overwrite your local game configuration files.\n"
            "Are you sure you want to continue?",
        ):
            return

        self._set_scanning(True)
        self._status_label.configure(text="Importing configuration…")
        threading.Thread(
            target=self._do_import,
            args=(package_path,),
            daemon=True,
        ).start()

    def _do_import(self, package_path: str) -> None:
        try:
            restored = self._package.import_package(package_path)
            count = sum(len(v) for v in restored.values())
            self.root.after(
                0,
                messagebox.showinfo,
                "Import Complete",
                f"Restored {count} config file(s) across {len(restored)} game(s).",
            )
        except Exception as exc:
            self.root.after(
                0,
                messagebox.showerror,
                "Import Failed",
                str(exc),
            )
        finally:
            self.root.after(0, self._set_scanning, False)
            self.root.after(
                0,
                self._status_label.configure,
                {"text": f"{len(self._game_rows)} game(s) found."},
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the Tkinter event loop."""
        self.root.mainloop()
