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
from config_manager.config_exporter import (
    _try_read_file,
    _read_registry_key,
    _is_expanded_registry_path,
    _scan_directory,
)
from config_manager.settings_parser import (
    extract_key_settings,
    ALL_KEYS,
    DISPLAY_NAMES,
    DISPLAY_NAMES_EN,
    SETTING_OPTIONS,
)
from config_manager.settings_writer import write_settings


# Sentinel used by GameRow.update_config_status to indicate a failed wiki lookup.
_UNABLE_TO_CHECK = object()


def _require_ctk() -> None:
    if ctk is None:
        raise ImportError(
            "customtkinter is required to run the GUI. "
            "Install it with: pip install customtkinter"
        )


class GameRow:
    """A single row in the game list with checkbox, status, and expandable settings panel."""

    # Setting key → icon for visual indicator
    _SETTING_ICONS = {
        "resolution": "🖥️",
        "screen_mode": "🪟",
        "vsync": "🔄",
        "frame_limit": "⏱️",
        "dynamic_resolution": "📐",
        "upscaling": "🔍",
        "frame_generation": "🎞️",
    }

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
        self._expanded = False
        self._key_settings: Optional[Dict[str, Optional[str]]] = None
        self._config_dicts: List[Dict[str, Any]] = []  # raw config file data for write-back
        self._setting_vars: Dict[str, ctk.StringVar] = {}  # dropdown variables

        self.var = ctk.BooleanVar(value=False)

        # Outer container – frosted glass card
        self._outer_frame = ctk.CTkFrame(
            parent, corner_radius=10,
            fg_color=("#e8eaed", "#1e1e2e"),
            border_width=1,
            border_color=("#c0c0c0", "#333346"),
        )
        self._outer_frame.pack(fill="x", padx=6, pady=3)

        # Header row (checkbox + status)
        self.frame = ctk.CTkFrame(self._outer_frame, corner_radius=0, fg_color="transparent")
        self.frame.pack(fill="x", padx=0, pady=0)

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

        # Expand/collapse button
        self._toggle_btn = ctk.CTkButton(
            self.frame,
            text="▶",
            width=28,
            height=24,
            font=ctk.CTkFont(size=11),
            fg_color=("#d0d0d0", "#2a2a3d"),
            hover_color=("#c0c0c0", "#3a3a50"),
            text_color=("#333", "#aaa"),
            command=self._toggle_details,
        )
        self._toggle_btn.pack(side="right", padx=2, pady=4)
        self._toggle_btn.pack_forget()  # Hidden until settings available

        # Detail panel (initially hidden) – frosted glass inner panel
        self._detail_frame = ctk.CTkFrame(
            self._outer_frame,
            corner_radius=6,
            fg_color=("#dde0e4", "#16161e"),
            border_width=1,
            border_color=("#b8b8b8", "#2a2a3a"),
        )
        self._setting_labels: Dict[str, ctk.CTkLabel] = {}

        self.update_config_status(config_files)

    def _toggle_details(self) -> None:
        """Toggle the visibility of the key settings panel."""
        if self._expanded:
            self._detail_frame.pack_forget()
            self._toggle_btn.configure(text="▶")
        else:
            self._detail_frame.pack(fill="x", padx=8, pady=(0, 6))
            self._toggle_btn.configure(text="▼")
        self._expanded = not self._expanded

    def _build_settings_panel(self) -> None:
        """Populate the detail panel with key settings dropdowns.

        Only settings that have a detected value (not None) are shown.
        Settings with value "N/A" are shown as read-only without a dropdown.
        """
        # Clear previous content
        for w in self._detail_frame.winfo_children():
            w.destroy()
        self._setting_labels.clear()
        self._setting_vars.clear()

        if not self._key_settings:
            return

        # Filter to only supported settings (non-None)
        supported_keys = [k for k in ALL_KEYS if self._key_settings.get(k) is not None]
        if not supported_keys:
            return

        # Two-column grid layout
        grid_frame = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
        grid_frame.pack(fill="x", padx=4, pady=4)

        half = (len(supported_keys) + 1) // 2  # split roughly in half

        for i, key in enumerate(supported_keys):
            col = 0 if i < half else 3
            row = i if i < half else i - half

            icon = self._SETTING_ICONS.get(key, "")
            display = DISPLAY_NAMES_EN.get(key, key)
            value = self._key_settings.get(key)

            name_label = ctk.CTkLabel(
                grid_frame,
                text=f"{icon} {display}",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("#555", "#8888aa"),
                anchor="w",
                width=130,
            )
            name_label.grid(row=row, column=col, sticky="w", padx=(8, 2), pady=1)

            # Current value label
            if value == "N/A":
                display_val = "N/A"
                color = ("#999", "#555566")
            else:
                display_val = value
                color = ("#1a8a4a", "#5af0a0")

            val_label = ctk.CTkLabel(
                grid_frame,
                text=display_val,
                font=ctk.CTkFont(size=11),
                text_color=color,
                anchor="w",
                width=140,
            )
            val_label.grid(row=row, column=col + 1, sticky="w", padx=(2, 4), pady=1)
            self._setting_labels[key] = val_label

            # Dropdown — only for editable settings (not N/A)
            if value != "N/A":
                options = SETTING_OPTIONS.get(key, ["—"])
                var = ctk.StringVar(value="—")
                self._setting_vars[key] = var

                dropdown = ctk.CTkOptionMenu(
                    grid_frame,
                    variable=var,
                    values=options,
                    width=120,
                    height=22,
                    font=ctk.CTkFont(size=10),
                    dropdown_font=ctk.CTkFont(size=10),
                    fg_color=("#c8c8d0", "#2a2a3d"),
                    button_color=("#b0b0b8", "#3a3a50"),
                    button_hover_color=("#a0a0a8", "#4a4a60"),
                    dropdown_fg_color=("#e0e0e0", "#222233"),
                    dropdown_hover_color=("#d0d0d8", "#333346"),
                    text_color=("#333", "#ccc"),
                )
                dropdown.grid(row=row, column=col + 2, sticky="w", padx=(2, 8), pady=1)

        # Apply button row
        btn_frame = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=4, pady=(2, 4))

        self._apply_btn = ctk.CTkButton(
            btn_frame,
            text="✏️  Apply Changes",
            width=140,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color=("#2b8a3e", "#2b6b3e"),
            hover_color=("#237032", "#1f5530"),
            command=self._apply_settings,
        )
        self._apply_btn.pack(side="right", padx=8)

    def update_key_settings(self, settings: Dict[str, Optional[str]]) -> None:
        """Update the key settings data and rebuild the panel."""
        self._key_settings = settings
        self._build_settings_panel()
        # Show expand button if we have any settings
        if any(v is not None for v in settings.values()):
            self._toggle_btn.pack(side="right", padx=2, pady=4)
            # Auto-expand to show settings
            if not self._expanded:
                self._toggle_details()

    def update_config_dicts(self, config_dicts: List[Dict[str, Any]]) -> None:
        """Store the raw config file data for write-back."""
        self._config_dicts = config_dicts

    def get_pending_changes(self) -> Dict[str, Optional[str]]:
        """Return a dict of settings the user has changed (dropdown != '—')."""
        changes: Dict[str, Optional[str]] = {}
        for key, var in self._setting_vars.items():
            val = var.get()
            if val != "—":
                changes[key] = val
        return changes

    def _apply_settings(self) -> None:
        """Apply the dropdown changes to this game's config files."""
        changes = self.get_pending_changes()
        if not changes:
            messagebox.showinfo("No Changes", f"No settings changed for {self.game_name}.")
            return

        if not self._config_dicts:
            messagebox.showwarning(
                "No Config Data",
                f"No config file data available for {self.game_name}.\n"
                "Config files must be detected first.",
            )
            return

        result = write_settings(self.game_name, self._config_dicts, changes)
        ok_count = sum(1 for r in result if r["status"] == "ok")
        errors = [r for r in result if r["status"] == "error"]

        if errors:
            msg = "\n".join(f"  • {e['path']}: {e['detail']}" for e in errors)
            messagebox.showerror(
                "Apply Failed",
                f"Errors writing settings for {self.game_name}:\n{msg}",
            )
        elif ok_count > 0:
            # Update the display labels to show the new values
            for key, val in changes.items():
                if key in self._setting_labels:
                    self._setting_labels[key].configure(
                        text=val, text_color=("#1a8a4a", "#5af0a0")
                    )
                # Update internal state
                if self._key_settings:
                    self._key_settings[key] = val
            messagebox.showinfo(
                "Applied",
                f"Settings applied for {self.game_name} ({ok_count} file(s) updated).",
            )
        else:
            messagebox.showinfo(
                "No Files Written",
                f"No config files were modified for {self.game_name}.\n"
                "The game's config format may not be supported for writing yet.",
            )

    def update_config_status(self, config_files: Any) -> None:
        """Update the config file status label.

        Parameters
        ----------
        config_files:
            ``None``               → still querying (shows "🔄 Checking…")
            ``_UNABLE_TO_CHECK``   → wiki lookup failed (shows "Unable to check")
            ``[]``                 → query done, no config files found locally
            ``[path, …]``         → query done, one or more config files found
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
        self.root.title("Game Setting Aligner v0.05.1")
        self.root.geometry("960x700")
        self.root.minsize(800, 500)

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

        # ── Global Settings Panel ──
        self._global_frame = ctk.CTkFrame(
            self.root, corner_radius=8,
            fg_color=("#e0e3e8", "#1a1a2a"),
            border_width=1,
            border_color=("#b0b0b0", "#333346"),
        )
        self._global_frame.pack(fill="x", padx=16, pady=(8, 0))

        global_header = ctk.CTkFrame(self._global_frame, fg_color="transparent")
        global_header.pack(fill="x", padx=4, pady=(4, 0))

        ctk.CTkLabel(
            global_header,
            text="⚙️  Global Settings",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left", padx=8)

        self._global_apply_btn = ctk.CTkButton(
            global_header,
            text="⚡ Apply to All Supported Games",
            width=220,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color=("#2b8a3e", "#2b6b3e"),
            hover_color=("#237032", "#1f5530"),
            command=self._global_apply,
        )
        self._global_apply_btn.pack(side="right", padx=8, pady=4)

        global_grid = ctk.CTkFrame(self._global_frame, fg_color="transparent")
        global_grid.pack(fill="x", padx=4, pady=(2, 6))

        self._global_vars: Dict[str, ctk.StringVar] = {}
        for i, key in enumerate(ALL_KEYS):
            col = (i % 4) * 2
            row = i // 4

            icon = GameRow._SETTING_ICONS.get(key, "")
            display = DISPLAY_NAMES_EN.get(key, key)

            ctk.CTkLabel(
                global_grid,
                text=f"{icon} {display}",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("#555", "#8888aa"),
                anchor="w",
                width=120,
            ).grid(row=row, column=col, sticky="w", padx=(8, 2), pady=2)

            options = SETTING_OPTIONS.get(key, ["—"])
            var = ctk.StringVar(value="—")
            self._global_vars[key] = var

            ctk.CTkOptionMenu(
                global_grid,
                variable=var,
                values=options,
                width=120,
                height=24,
                font=ctk.CTkFont(size=10),
                dropdown_font=ctk.CTkFont(size=10),
                fg_color=("#c8c8d0", "#2a2a3d"),
                button_color=("#b0b0b8", "#3a3a50"),
                button_hover_color=("#a0a0a8", "#4a4a60"),
                dropdown_fg_color=("#e0e0e0", "#222233"),
                dropdown_hover_color=("#d0d0d8", "#333346"),
                text_color=("#333", "#ccc"),
            ).grid(row=row, column=col + 1, sticky="w", padx=(2, 12), pady=2)

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

        self._batch_apply_btn = ctk.CTkButton(
            action_bar,
            text="⚡  Batch Apply All",
            width=150,
            fg_color=("#2b8a3e", "#2b6b3e"),
            hover_color=("#237032", "#1f5530"),
            command=self._batch_apply,
        )
        self._batch_apply_btn.pack(side="right", padx=4, pady=8)

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
            row._outer_frame.destroy()
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
            install_path = getattr(game, "install_path", "")
            try:
                wiki_info = self._wiki_client.get_config_info(game_name, install_path=install_path)
                expanded_paths = wiki_info.get("expanded_paths") or []
                found_files = detect_config_files(expanded_paths)

                # Build config_files dicts (same format as export JSON)
                # so extract_key_settings can parse them.
                config_dicts = []
                for path in expanded_paths:
                    if _is_expanded_registry_path(path):
                        config_dicts.append(_read_registry_key(path))
                    elif os.path.isdir(path):
                        for fp in _scan_directory(path):
                            config_dicts.append(_try_read_file(fp))
                    elif os.path.isfile(path):
                        config_dicts.append(_try_read_file(path))

                settings = extract_key_settings(game_name, config_dicts)
            except Exception:
                # Graceful degradation: network errors, timeouts, parsing
                # failures, etc. should not crash the background thread.
                return game_name, _UNABLE_TO_CHECK, None, []
            return game_name, found_files, settings, config_dicts

        def _run_all() -> None:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_game = {
                    executor.submit(_detect, game): game for game in games
                }
                for future in concurrent.futures.as_completed(future_to_game):
                    try:
                        game_name, result, settings, config_dicts = future.result()
                    except Exception:
                        # Defensive catch: future.result() itself should not
                        # raise since _detect handles its own errors, but guard
                        # against any unexpected executor-level failures.
                        game = future_to_game[future]
                        game_name = getattr(game, "name", str(game))
                        result = _UNABLE_TO_CHECK
                        settings = None
                        config_dicts = []

                    row = rows_by_name.get(game_name)
                    if row is not None:
                        self.root.after(0, row.update_config_status, result)
                        if settings is not None:
                            self.root.after(0, row.update_key_settings, settings)
                        if config_dicts:
                            self.root.after(0, row.update_config_dicts, config_dicts)

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
            self.root.after(0, self._on_export_success, output_path)
        except Exception as exc:
            self.root.after(0, self._on_export_error, str(exc))

    def _on_export_success(self, output_path: str) -> None:
        self._set_scanning(False)
        self._status_label.configure(
            text=f"{len(self._game_rows)} game(s) found."
        )
        messagebox.showinfo(
            "Export Complete",
            f"Config package saved to:\n{output_path}",
        )

    def _on_export_error(self, error_msg: str) -> None:
        self._set_scanning(False)
        self._status_label.configure(
            text=f"{len(self._game_rows)} game(s) found."
        )
        messagebox.showerror("Export Failed", error_msg)

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

    def _global_apply(self) -> None:
        """Apply global settings to all games that support each changed setting."""
        # Gather which global settings the user changed
        global_changes: Dict[str, str] = {}
        for key, var in self._global_vars.items():
            val = var.get()
            if val != "—":
                global_changes[key] = val

        if not global_changes:
            messagebox.showinfo(
                "No Changes",
                "No global settings have been selected.\n"
                "Use the dropdowns in the Global Settings panel to choose values.",
            )
            return

        # Find all games that support each changed setting
        applicable: List[GameRow] = []
        for row in self._game_rows:
            if not row._config_dicts or not row._key_settings:
                continue
            # Only apply settings that the game actually supports (not None, not N/A)
            game_applicable = {
                k: v for k, v in global_changes.items()
                if row._key_settings.get(k) is not None and row._key_settings.get(k) != "N/A"
            }
            if game_applicable:
                applicable.append(row)

        if not applicable:
            messagebox.showinfo(
                "No Applicable Games",
                "No games found that support the selected settings.\n"
                "Games need detected config files to apply settings.",
            )
            return

        settings_desc = ", ".join(
            f"{DISPLAY_NAMES_EN.get(k, k)}: {v}" for k, v in global_changes.items()
        )
        game_list = "\n".join(f"  • {row.game_name}" for row in applicable)
        if not messagebox.askyesno(
            "Confirm Global Apply",
            f"Apply these settings to {len(applicable)} game(s)?\n\n"
            f"Settings: {settings_desc}\n\n{game_list}",
        ):
            return

        total_ok = 0
        total_err = 0
        error_details: List[str] = []

        for row in applicable:
            # Only apply supported settings for this game
            game_changes = {
                k: v for k, v in global_changes.items()
                if row._key_settings
                and row._key_settings.get(k) is not None
                and row._key_settings.get(k) != "N/A"
            }
            if not game_changes:
                continue

            result = write_settings(row.game_name, row._config_dicts, game_changes)
            for r in result:
                if r["status"] == "ok":
                    total_ok += 1
                    for key, val in game_changes.items():
                        if key in row._setting_labels:
                            row._setting_labels[key].configure(
                                text=val, text_color=("#1a8a4a", "#5af0a0")
                            )
                        if row._key_settings:
                            row._key_settings[key] = val
                elif r["status"] == "error":
                    total_err += 1
                    error_details.append(f"{row.game_name}: {r['detail']}")

        if error_details:
            msg = "\n".join(f"  • {e}" for e in error_details)
            messagebox.showwarning(
                "Global Apply Partial",
                f"Applied to {total_ok} file(s), {total_err} error(s):\n\n{msg}",
            )
        else:
            messagebox.showinfo(
                "Global Apply Complete",
                f"Successfully applied settings to {total_ok} config file(s) "
                f"across {len(applicable)} game(s).",
            )

    def _batch_apply(self) -> None:
        """Apply dropdown changes across all games that have pending changes."""
        applicable = []
        for row in self._game_rows:
            changes = row.get_pending_changes()
            if changes and row._config_dicts:
                applicable.append(row)

        if not applicable:
            messagebox.showinfo(
                "No Changes",
                "No settings have been changed in any game's dropdown.\n"
                "Use the dropdowns next to each setting to select new values.",
            )
            return

        game_list = "\n".join(f"  • {row.game_name}" for row in applicable)
        if not messagebox.askyesno(
            "Confirm Batch Apply",
            f"Apply setting changes to {len(applicable)} game(s)?\n\n{game_list}",
        ):
            return

        total_ok = 0
        total_err = 0
        error_details: List[str] = []

        for row in applicable:
            changes = row.get_pending_changes()
            result = write_settings(row.game_name, row._config_dicts, changes)
            for r in result:
                if r["status"] == "ok":
                    total_ok += 1
                    # Update display labels
                    for key, val in changes.items():
                        if key in row._setting_labels:
                            row._setting_labels[key].configure(
                                text=val, text_color=("#1a8a4a", "#5af0a0")
                            )
                        if row._key_settings:
                            row._key_settings[key] = val
                elif r["status"] == "error":
                    total_err += 1
                    error_details.append(f"{row.game_name}: {r['detail']}")

        if error_details:
            msg = "\n".join(f"  • {e}" for e in error_details)
            messagebox.showwarning(
                "Batch Apply Partial",
                f"Applied to {total_ok} file(s), {total_err} error(s):\n\n{msg}",
            )
        else:
            messagebox.showinfo(
                "Batch Apply Complete",
                f"Successfully applied settings to {total_ok} config file(s) "
                f"across {len(applicable)} game(s).",
            )

    def run(self) -> None:
        """Start the Tkinter event loop."""
        self.root.mainloop()
