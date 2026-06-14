# Changelog

## v0.05.1 (2026-06-14)

### New Features
- **Global Settings Panel**: New top-level panel with dropdowns for all 7 settings — apply once, write to all supported games via "⚡ Apply to All Supported Games" button
- **Smart Dropdown Filtering**: Per-game settings panels now only show dropdowns for settings the game actually supports; `N/A` settings shown as read-only labels, unsupported (`None`) settings hidden entirely

### Bug Fixes
- **`{{P|game}}` expansion**: Now correctly substitutes the game's install path instead of expanding to an empty string
- **`{{P|userprofile/appdata/locallow}}`**: Added missing token mapping for Unity LocalLow config paths (e.g. Sons Of The Forest)
- **Wiki markup in paths**: Strip `''(version info)''` italic markup from config paths returned by PCGamingWiki
- **™/®/© in game titles**: Retry wiki lookups with cleaned titles and search API fallback when special characters cause lookup failures (e.g. Horizon Zero Dawn™ Remastered)

### Files Changed
- `main.py` — Version bump to 0.05.1
- `gui/app.py` — Global settings panel, smart dropdown filtering, window 960×700
- `wiki_api/pcgamingwiki.py` — `install_path` parameter, `locallow` token, wiki markup stripping, ™/® retry logic

---

## v0.05 (2026-06-12)

### New Features
- **Settings Editor**: Each game's expandable panel now shows editable dropdown menus alongside the current value for all 7 key settings (Resolution, Screen Mode, VSync, Frame Limit, Dynamic Resolution, Upscaling, Frame Generation)
- **Per-Game Apply**: "✏️ Apply Changes" button in each game's settings panel writes dropdown selections back to the actual config files on disk
- **Batch Apply All**: "⚡ Batch Apply All" button in the action bar applies pending changes across all games at once
- **Settings Writer Module** (`config_manager/settings_writer.py`): New module with format-specific writers:
  - `_write_cyberpunk()` — JSON (Cyberpunk 2077 UserSettings.json)
  - `_write_unreal_ini()` — INI (Unreal Engine games)
  - `_write_forza_xml()` — XML (Forza Horizon series)
  - `_write_registry_json()` — Registry (HZD Remastered, Shadow of the Tomb Raider)
  - `_write_cs2_video()` — Valve KV (Counter-Strike 2)
- **Setting Options** (`SETTING_OPTIONS`): Predefined dropdown choices for each setting key

### Files Changed
- `main.py` — Version bump to 0.05
- `config_manager/__init__.py` — Export `SETTING_OPTIONS`, `write_settings`
- `config_manager/settings_parser.py` — Added `SETTING_OPTIONS` dict
- `config_manager/settings_writer.py` — **NEW** Settings write-back module
- `gui/app.py` — GameRow dropdowns, Apply button, Batch Apply, wider window (960x650)

---

## v0.04.1 (2026-06-05)

### Verified Games (tested on workstation)

| Game | Config Found | Config Path |
|------|-------------|-------------|
| Baldur's Gate 3 | ✅ | `{{p|localappdata}}\Larian Studios\Baldur's Gate 3\graphicSettings.lsx` |
| Cyberpunk 2077 | ✅ | `{{P|localappdata}}\CD Projekt Red\Cyberpunk 2077\UserSettings.json` |
| Hades II | ✅ | `{{p|userprofile}}\Saved Games\Hades II\GlobalSettingsWin.sjson` |
| Apex Legends | ✅ | `{{P|userprofile}}\Saved Games\Respawn\Apex\local\videoconfig.txt` (+ 2 more) |
| Red Dead Redemption 2 | ✅ | `{{P|userprofile\Documents}}\Rockstar Games\Red Dead Redemption 2\Settings\system.xml` |
| Black Myth: Wukong | ✅ | `{{p|localappdata}}\b1\Saved\Config\Windows\GameUserSettings.ini` (+ 26 more) |
| Horizon Zero Dawn™ Remastered | ✅ | `{{p|userprofile\documents}}\Horizon Zero Dawn Remastered\profile.dat` |

### Cache Updated
- Added **Baldur's Gate 3**, **Hades II**, **Apex Legends** to `cache/wiki_cache.json`
- Added 27 more games from PCGamingWiki verification: Total War: Warhammer III, Horizon Zero Dawn, Naraka: Bladepoint, Elden Ring, Sons of the Forest, Street Fighter 6, Palworld, Starfield, Nine Sols, The Finals, EA Sports FC 24, Horizon Forbidden West, F1 24, Marvel Rivals, Strange Brigade, Monster Hunter Wilds, Tom Clancy's Rainbow Six Siege, Fallout 4, Dying Light 2, Helldivers 2, Dota 2, PUBG: Battlegrounds, Hogwarts Legacy, Hollow Knight: Silksong, Metro Exodus, Resident Evil 6, Grand Theft Auto V Enhanced
- Total cache: 49 games

---

## v0.04 (2026-06-05)

### New Features
- **Key Settings Panel**: Added expandable settings panel in each GameRow showing 7 key graphics settings:
  - Resolution, Screen Mode, VSync, Frame Limit, Dynamic Resolution, Upscaling, Frame Generation
- **Settings Parser** (`config_manager/settings_parser.py`): New module with dedicated parsers for multiple config formats:
  - `_parse_cyberpunk()` — JSON (Cyberpunk 2077 UserSettings.json)
  - `_parse_unreal_ini()` — INI (Unreal Engine games like ARC Raiders)
  - `_parse_forza_xml()` — XML (Forza Horizon 6 UserConfigSelections)
  - `_parse_registry_json()` — Registry JSON (Horizon Zero Dawn Remastered, Shadow of the Tomb Raider)
  - `_parse_cs2()` — Valve KeyValues (Counter-Strike 2 multi-file configs)
- **Frosted Glass Dark Theme**: Full visual redesign with frosted glass dark theme for GUI
- **English Labels**: All UI labels switched to English (`DISPLAY_NAMES_EN`)
- **Simulation Tool** (`tools/simulate_gui.py`): Standalone GUI preview tool with frosted glass theme
- **Config Import v2 Support**: `ConfigPackage.import_package()` now supports both v1 and v2 package formats

### Bug Fixes
- Fixed Cyberpunk 2077 VSync localization key display (now shows "Off"/"On" instead of raw `LocKey`)
- Fixed Shadow of the Tomb Raider Frame Generation showing `None` instead of `N/A`
- Fixed "Unsupported package version 2" error when importing configs exported by v0.04
- Fixed v2 import to write raw content back to files (skips registry entries and binary files)

### Verified Games (tested on real machine — MVT-PR4)

| Game | Config Format | Key Settings Extracted |
|------|--------------|----------------------|
| Cyberpunk 2077 | JSON (`UserSettings.json`) | Resolution, Screen Mode, VSync, Frame Limit, Dynamic Resolution, Upscaling (XeSS), Frame Generation (XESS/MFG) |
| ARC Raiders | Unreal INI (`GameUserSettings.ini`) | Resolution, Screen Mode, VSync, Frame Limit, Dynamic Resolution, Upscaling (XeSS), Frame Generation |
| Forza Horizon 6 | XML (`UserConfigSelections`) | Resolution, Screen Mode, VSync, Frame Limit, Dynamic Resolution, Upscaling (XeSS), Frame Generation |
| Horizon Zero Dawn™ Remastered | Registry + binary `profile.dat` | Resolution, Screen Mode, VSync, Frame Limit, Dynamic Resolution, Upscaling (XeSS), Frame Generation |
| Counter-Strike 2 | Valve KV (`.vcfg` + `.txt`, multi-file) | Resolution, Screen Mode, VSync, Frame Limit, Dynamic Resolution (N/A), Upscaling, Frame Generation (N/A) |
| Shadow of the Tomb Raider | Registry JSON | Resolution, Screen Mode, VSync, Frame Limit, Dynamic Resolution, Upscaling (XeSS), Frame Generation (N/A) |

> **Note**: "Steamworks Common Redistributables" is detected by Steam but has no config files (expected behavior).

### Files Changed
- `main.py` — Version bump to 0.04
- `config_manager/__init__.py` — Updated exports for new functions
- `config_manager/settings_parser.py` — **NEW** Key settings extraction module
- `config_manager/package.py` — Added v2 import support (`SUPPORTED_VERSIONS`, `_import_v2`)
- `config_manager/config_exporter.py` — v2 export format with config file contents
- `gui/app.py` — GameRow redesign with key settings panel, frosted glass theme, English labels
- `tools/simulate_gui.py` — **NEW** Standalone GUI simulation tool
- `wiki_api/pcgamingwiki.py` — Wiki API improvements
- `tests/test_config_exporter.py` — Test updates
- `tests/test_wiki_api.py` — Test updates
- `validation/test6.json` — **NEW** Real machine test data (export)
- `validation/test7.json` — **NEW** Real machine test data (import test)

---

## v0.03 (2026-06-04)

- Wiki cache system for offline operation
- Config file detection and status display in GUI
- Path token expansion fixes and diagnostic tools

## v0.02

- Initial GUI with CustomTkinter
- PCGamingWiki API integration
- Config file reading/writing (JSON, XML, INI)

## v0.01

- Project scaffolding
- Basic config reader/writer
- PyInstaller packaging setup
