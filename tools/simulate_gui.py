"""Simulate the GUI key settings display using test7.json data.

Run this script to preview how the new key settings panel looks
with real config data from the offline test machine.
"""

from __future__ import annotations

import json
import os
import sys

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import customtkinter as ctk
except ImportError:
    print("ERROR: customtkinter is required. Install with: pip install customtkinter")
    sys.exit(1)

from config_manager.settings_parser import (
    extract_key_settings,
    ALL_KEYS,
    DISPLAY_NAMES_EN,
)

# ── Style constants ──────────────────────────────────────────────────

_SETTING_ICONS = {
    "resolution": "🖥️",
    "screen_mode": "🪟",
    "vsync": "🔄",
    "frame_limit": "⏱️",
    "dynamic_resolution": "📐",
    "upscaling": "🔍",
    "frame_generation": "🎞️",
}

# Frosted glass dark palette
_BG_WINDOW = "#0d0d14"
_BG_CARD = "#1a1a28"
_BG_CARD_BORDER = "#2c2c40"
_BG_DETAIL = "#13131c"
_BG_DETAIL_BORDER = "#262638"
_BG_SUMMARY = "#141420"
_BG_SUMMARY_BORDER = "#2a2a3e"

_TEXT_PRIMARY = "#e0e0f0"
_TEXT_SECONDARY = "#8888aa"
_TEXT_DIM = "#555568"
_TEXT_GREEN = "#5af0a0"
_TEXT_YELLOW = "#e8c840"
_TEXT_STATUS_OK = "#4ad8a0"


def main() -> None:
    # Load test7.json
    test_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "validation",
        "test7.json",
    )
    if not os.path.isfile(test_path):
        print(f"ERROR: {test_path} not found. Please run export first.")
        sys.exit(1)

    with open(test_path, "r", encoding="utf-8") as fh:
        package = json.load(fh)

    games = package.get("games", {})

    # ── Build GUI ────────────────────────────────────────────────────

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("Game Setting Aligner v0.04 — Preview")
    root.geometry("920x720")
    root.minsize(720, 520)
    root.configure(fg_color=_BG_WINDOW)

    # ── Top bar ──────────────────────────────────────────────────────

    top_bar = ctk.CTkFrame(root, corner_radius=0, fg_color="#111118")
    top_bar.pack(fill="x")

    title = ctk.CTkLabel(
        top_bar,
        text="⚙  Game Setting Aligner",
        font=ctk.CTkFont(family="Segoe UI", size=19, weight="bold"),
        text_color=_TEXT_PRIMARY,
    )
    title.pack(side="left", padx=16, pady=10)

    ver_lbl = ctk.CTkLabel(
        top_bar,
        text="v0.04",
        font=ctk.CTkFont(size=11),
        text_color=_TEXT_DIM,
    )
    ver_lbl.pack(side="left", padx=0, pady=10)

    # ── Status ───────────────────────────────────────────────────────

    status = ctk.CTkLabel(
        root,
        text=f"Loaded {len(games)} game(s) from test7.json  ·  Key settings preview",
        font=ctk.CTkFont(size=11),
        text_color=_TEXT_SECONDARY,
    )
    status.pack(anchor="w", padx=18, pady=(6, 0))

    # ── Scrollable game list ─────────────────────────────────────────

    scroll = ctk.CTkScrollableFrame(
        root,
        label_text="Installed Games — Key Graphics Settings",
        label_font=ctk.CTkFont(size=13, weight="bold"),
        fg_color="#0f0f18",
        scrollbar_button_color="#2a2a3d",
        scrollbar_button_hover_color="#3a3a50",
    )
    scroll.pack(fill="both", expand=True, padx=14, pady=8)

    skip_names = {"Steamworks Common Redistributables"}

    for game_name, game_data in games.items():
        if game_name in skip_names:
            continue

        config_files = game_data.get("config_files", [])
        readable_count = sum(1 for c in config_files if c.get("found"))
        settings = extract_key_settings(game_name, config_files)

        # ── Game card (frosted glass) ────────────────────────────────

        card = ctk.CTkFrame(
            scroll,
            corner_radius=10,
            fg_color=_BG_CARD,
            border_width=1,
            border_color=_BG_CARD_BORDER,
        )
        card.pack(fill="x", padx=4, pady=4)

        # Header row
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=0, pady=0)

        platform = game_data.get("platform", "Unknown")
        name_label = ctk.CTkLabel(
            header,
            text=f"☑  {game_name}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=_TEXT_PRIMARY,
            anchor="w",
        )
        name_label.pack(side="left", padx=10, pady=5)

        plat_label = ctk.CTkLabel(
            header,
            text=f"[{platform}]",
            font=ctk.CTkFont(size=11),
            text_color=_TEXT_DIM,
            anchor="w",
        )
        plat_label.pack(side="left", padx=0, pady=5)

        status_text = f"✅ {readable_count} config(s)" if readable_count else "⚠️ No config"
        status_color = _TEXT_STATUS_OK if readable_count else _TEXT_YELLOW
        ctk.CTkLabel(
            header,
            text=status_text,
            font=ctk.CTkFont(size=10),
            text_color=status_color,
        ).pack(side="right", padx=10, pady=5)

        # ── Settings detail panel (frosted glass inner) ──────────────

        detail = ctk.CTkFrame(
            card,
            corner_radius=6,
            fg_color=_BG_DETAIL,
            border_width=1,
            border_color=_BG_DETAIL_BORDER,
        )
        detail.pack(fill="x", padx=8, pady=(0, 7))

        grid = ctk.CTkFrame(detail, fg_color="transparent")
        grid.pack(fill="x", padx=6, pady=5)

        for i, key in enumerate(ALL_KEYS):
            col = 0 if i < 4 else 2
            row = i if i < 4 else i - 4

            icon = _SETTING_ICONS.get(key, "")
            display = DISPLAY_NAMES_EN.get(key, key)
            value = settings.get(key)

            ctk.CTkLabel(
                grid,
                text=f"{icon} {display}",
                font=ctk.CTkFont(size=11),
                text_color=_TEXT_SECONDARY,
                anchor="w",
                width=140,
            ).grid(row=row, column=col, sticky="w", padx=(6, 2), pady=1)

            if value is None:
                dv, clr = "—", _TEXT_DIM
            elif value == "N/A":
                dv, clr = "N/A", _TEXT_DIM
            else:
                dv, clr = str(value), _TEXT_GREEN

            ctk.CTkLabel(
                grid,
                text=dv,
                font=ctk.CTkFont(size=11),
                text_color=clr,
                anchor="w",
                width=200,
            ).grid(row=row, column=col + 1, sticky="w", padx=(2, 14), pady=1)

    # ── Summary section ──────────────────────────────────────────────

    summary_frame = ctk.CTkFrame(
        root,
        corner_radius=8,
        fg_color=_BG_SUMMARY,
        border_width=1,
        border_color=_BG_SUMMARY_BORDER,
    )
    summary_frame.pack(fill="x", padx=14, pady=(0, 10))

    ctk.CTkLabel(
        summary_frame,
        text="Coverage Matrix",
        font=ctk.CTkFont(size=12, weight="bold"),
        text_color=_TEXT_PRIMARY,
    ).pack(anchor="w", padx=10, pady=(6, 2))

    sg = ctk.CTkFrame(summary_frame, fg_color="transparent")
    sg.pack(fill="x", padx=6, pady=(0, 6))

    # Header row
    ctk.CTkLabel(
        sg, text="Setting",
        font=ctk.CTkFont(size=9, weight="bold"),
        text_color=_TEXT_SECONDARY, width=110,
    ).grid(row=0, column=0, padx=2)

    game_names = [n for n in games if n not in skip_names]
    for j, gn in enumerate(game_names):
        short = gn[:14] + "…" if len(gn) > 15 else gn
        ctk.CTkLabel(
            sg, text=short,
            font=ctk.CTkFont(size=8, weight="bold"),
            text_color=_TEXT_SECONDARY, width=95,
        ).grid(row=0, column=j + 1, padx=1)

    for i, key in enumerate(ALL_KEYS):
        display = DISPLAY_NAMES_EN.get(key, key)
        ctk.CTkLabel(
            sg, text=display,
            font=ctk.CTkFont(size=9),
            text_color=_TEXT_DIM, anchor="w", width=110,
        ).grid(row=i + 1, column=0, sticky="w", padx=4)

        for j, gn in enumerate(game_names):
            cfg = games[gn].get("config_files", [])
            s = extract_key_settings(gn, cfg)
            val = s.get(key)
            if val is None:
                sym, clr = "—", _TEXT_DIM
            elif val == "N/A":
                sym, clr = "N/A", _TEXT_DIM
            else:
                sym, clr = "✅", _TEXT_GREEN
            ctk.CTkLabel(
                sg, text=sym,
                font=ctk.CTkFont(size=9),
                text_color=clr, width=95,
            ).grid(row=i + 1, column=j + 1, padx=1)

    root.mainloop()


if __name__ == "__main__":
    main()
