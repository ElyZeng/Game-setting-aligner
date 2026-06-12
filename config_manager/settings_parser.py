"""Parse key graphics settings from game config file content.

Extracts 7 standardised settings from various config formats:
1. Resolution
2. Screen Mode
3. V-Sync
4. Frame Limit
5. Dynamic Resolution
6. Upscaling (DLSS / FSR / XeSS)
7. Frame Generation / Multi Frame Generation
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


# Result key constants
RESOLUTION = "resolution"
SCREEN_MODE = "screen_mode"
VSYNC = "vsync"
FRAME_LIMIT = "frame_limit"
DYNAMIC_RESOLUTION = "dynamic_resolution"
UPSCALING = "upscaling"
FRAME_GENERATION = "frame_generation"

ALL_KEYS = [
    RESOLUTION,
    SCREEN_MODE,
    VSYNC,
    FRAME_LIMIT,
    DYNAMIC_RESOLUTION,
    UPSCALING,
    FRAME_GENERATION,
]

# Human-readable display names (Chinese)
DISPLAY_NAMES = {
    RESOLUTION: "解析度",
    SCREEN_MODE: "螢幕模式",
    VSYNC: "垂直同步",
    FRAME_LIMIT: "幀率限制",
    DYNAMIC_RESOLUTION: "動態解析度",
    UPSCALING: "升頻技術",
    FRAME_GENERATION: "畫格生成",
}

DISPLAY_NAMES_EN = {
    RESOLUTION: "Resolution",
    SCREEN_MODE: "Screen Mode",
    VSYNC: "V-Sync",
    FRAME_LIMIT: "Frame Limit",
    DYNAMIC_RESOLUTION: "Dynamic Resolution",
    UPSCALING: "Upscaling",
    FRAME_GENERATION: "Frame Generation",
}

# Dropdown options for each setting.  The first value is the default /
# "no change" sentinel shown when the user has not explicitly picked a
# value.  The rest are the selectable choices.
SETTING_OPTIONS: Dict[str, List[str]] = {
    RESOLUTION: [
        "—",
        "1280x720",
        "1600x900",
        "1920x1080",
        "2560x1080",
        "2560x1440",
        "3440x1440",
        "3840x2160",
    ],
    SCREEN_MODE: [
        "—",
        "Fullscreen",
        "Borderless Windowed",
        "Windowed",
    ],
    VSYNC: [
        "—",
        "On",
        "Off",
    ],
    FRAME_LIMIT: [
        "—",
        "Unlimited",
        "30 FPS",
        "60 FPS",
        "120 FPS",
        "144 FPS",
        "240 FPS",
    ],
    DYNAMIC_RESOLUTION: [
        "—",
        "On",
        "Off",
    ],
    UPSCALING: [
        "—",
        "Off",
        "XeSS",
        "DLSS",
        "FSR",
    ],
    FRAME_GENERATION: [
        "—",
        "Off",
        "On",
    ],
}


def _empty_result() -> Dict[str, Optional[str]]:
    return {k: None for k in ALL_KEYS}


# ── Cyberpunk 2077 (UserSettings.json) ───────────────────────────────

def _parse_cyberpunk(content: str) -> Dict[str, Optional[str]]:
    r = _empty_result()
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return r

    groups = data.get("data", [])
    options_map: Dict[str, Any] = {}
    for group in groups:
        gname = group.get("group_name", "")
        for opt in group.get("options", []):
            key = f"{gname}/{opt['name']}"
            options_map[opt["name"]] = opt
            options_map[key] = opt

    # Resolution
    res_opt = options_map.get("/video/display/Resolution")
    if res_opt:
        r[RESOLUTION] = str(res_opt.get("value", ""))

    # Screen Mode
    wm = options_map.get("WindowMode") or options_map.get("/video/display/WindowMode")
    if wm:
        r[SCREEN_MODE] = str(wm.get("value", ""))

    # VSync
    vs = options_map.get("VSync") or options_map.get("/video/display/VSync")
    if vs:
        val = str(vs.get("value", ""))
        # Cyberpunk uses localization keys like "UI-Settings-Video-QualitySetting-Off"
        if "Off" in val:
            r[VSYNC] = "Off"
        elif "On" in val:
            r[VSYNC] = "On"
        else:
            r[VSYNC] = val

    # Frame Limit
    fps_on = options_map.get("MaximumFPS_OnOff")
    fps_val = options_map.get("MaximumFPS")
    if fps_on is not None:
        on = fps_on.get("value", False)
        limit = fps_val.get("value", "") if fps_val else ""
        r[FRAME_LIMIT] = f"{limit}" if on else "Off"

    # Dynamic Resolution
    drs = options_map.get("DynamicResolutionScaling")
    drs_fps = options_map.get("DRS_TargetFPS")
    if drs is not None:
        on = drs.get("value", False)
        target = drs_fps.get("value", "") if drs_fps else ""
        r[DYNAMIC_RESOLUTION] = f"On (Target: {target} FPS)" if on else "Off"

    # Upscaling
    rs = options_map.get("ResolutionScaling")
    if rs:
        method = str(rs.get("value", "Off"))
        # Try to get the quality of the active method
        quality = ""
        method_opt = options_map.get(method.upper()) or options_map.get(method)
        if method_opt:
            quality = f" ({method_opt.get('value', '')})"
        r[UPSCALING] = f"{method}{quality}"

    # Frame Generation
    fg = options_map.get("FrameGeneration")
    mfg = options_map.get("DLSS_MultiFrameGeneration")
    parts = []
    if fg:
        parts.append(str(fg.get("value", "Off")))
    if mfg:
        parts.append(f"MFG: {mfg.get('value', '')}")
    if parts:
        r[FRAME_GENERATION] = " / ".join(parts)

    return r


# ── Unreal Engine INI (ARC Raiders GameUserSettings.ini) ─────────────

def _parse_ini_kv(content: str) -> Dict[str, str]:
    """Parse simple key=value lines from INI-like content."""
    kv: Dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("[") and not line.startswith(";"):
            key, _, val = line.partition("=")
            kv[key.strip()] = val.strip()
    return kv


def _parse_unreal_ini(content: str) -> Dict[str, Optional[str]]:
    r = _empty_result()
    kv = _parse_ini_kv(content)

    # Resolution
    rx, ry = kv.get("ResolutionSizeX"), kv.get("ResolutionSizeY")
    if rx and ry:
        r[RESOLUTION] = f"{rx}x{ry}"

    # Screen Mode
    fm = kv.get("FullscreenMode")
    mode_map = {"0": "Fullscreen", "1": "Borderless Windowed", "2": "Windowed"}
    if fm is not None:
        r[SCREEN_MODE] = mode_map.get(fm, f"Mode {fm}")

    # VSync
    vs = kv.get("bUseVSync")
    if vs is not None:
        r[VSYNC] = "On" if vs.lower() == "true" else "Off"

    # Frame Limit
    frl = kv.get("FrameRateLimit")
    if frl is not None:
        try:
            val = float(frl)
            r[FRAME_LIMIT] = "Unlimited" if val <= 0 else f"{val:.0f} FPS"
        except ValueError:
            r[FRAME_LIMIT] = frl

    # Dynamic Resolution
    dr = kv.get("bUseDynamicResolution")
    if dr is not None:
        r[DYNAMIC_RESOLUTION] = "On" if dr.lower() == "true" else "Off"

    # Upscaling
    method = kv.get("ResolutionScalingMethod", "")
    dlss = kv.get("DLSSMode", "")
    fsr = kv.get("FSRMode", "")
    xess = kv.get("XeSSMode", "")
    if method:
        quality = {"DLSS": dlss, "FSR": fsr, "XeSS": xess}.get(method, "")
        r[UPSCALING] = f"{method} ({quality})" if quality else method

    # Frame Generation
    dlss_fg = kv.get("DLSSFrameGenerationMode", "")
    fsr_fg = kv.get("FSRFrameGenerationMode", "")
    parts = []
    if dlss_fg and dlss_fg != "Off":
        parts.append(f"DLSS FG: {dlss_fg}")
    if fsr_fg and fsr_fg != "Off":
        parts.append(f"FSR FG: {fsr_fg}")
    if dlss_fg or fsr_fg:
        r[FRAME_GENERATION] = " / ".join(parts) if parts else "Off"

    return r


# ── Forza Horizon XML (UserConfigSelections) ─────────────────────────

def _parse_forza_xml(content: str) -> Dict[str, Optional[str]]:
    r = _empty_result()

    def _xml_val(tag: str) -> Optional[str]:
        m = re.search(rf'<{tag}\b[^>]*\bvalue="([^"]*)"', content)
        return m.group(1) if m else None

    def _sel_val(option_id: str) -> Optional[str]:
        m = re.search(rf'<option\s+id="{option_id}"\s+value="([^"]*)"', content)
        return m.group(1) if m else None

    # Resolution
    rw, rh = _xml_val("ResolutionWidth"), _xml_val("ResolutionHeight")
    if rw and rh:
        r[RESOLUTION] = f"{rw}x{rh}"

    # Screen Mode
    fs = _xml_val("Fullscreen")
    if fs is not None:
        r[SCREEN_MODE] = "Fullscreen" if fs == "1" else "Windowed"

    # VSync
    vs = _sel_val("VSync")
    pi = _xml_val("PresentInterval")
    if vs is not None:
        r[VSYNC] = "On" if vs != "0" else "Off"
    elif pi is not None:
        r[VSYNC] = "Off" if pi == "0" else "On"

    # Frame Limit
    fr = _sel_val("FrameRate")
    if fr is not None:
        fr_map = {"0": "30 FPS", "1": "40 FPS", "2": "60 FPS", "3": "120 FPS", "4": "Unlimited"}
        r[FRAME_LIMIT] = fr_map.get(fr, f"Preset {fr}")

    # Dynamic Resolution
    dopt = _sel_val("UseDynamicOptimization")
    if dopt is not None:
        r[DYNAMIC_RESOLUTION] = "On" if dopt != "0" else "Off"

    # Upscaling
    dlss_sel = _sel_val("DLSSMode")
    fsr3_sel = _sel_val("FSR3Mode")
    xess_sel = _sel_val("XeSSMode")
    active = []
    if xess_sel and xess_sel != "0":
        active.append(f"XeSS (preset {xess_sel})")
    if dlss_sel and dlss_sel != "0":
        active.append(f"DLSS (preset {dlss_sel})")
    if fsr3_sel and fsr3_sel != "0":
        active.append(f"FSR3 (preset {fsr3_sel})")
    r[UPSCALING] = ", ".join(active) if active else "Off"

    # Frame Generation
    dlssg = _sel_val("DLSSGMode")
    fsr3_fg = _sel_val("FSR3Mode")
    parts = []
    if dlssg and dlssg != "0":
        parts.append(f"DLSS FG: On")
    r[FRAME_GENERATION] = ", ".join(parts) if parts else "Off"

    return r


# ── Registry JSON (HZD, Shadow of TR) ───────────────────────────────

def _parse_registry_json(content: str, game_hint: str = "") -> Dict[str, Optional[str]]:
    r = _empty_result()
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return r

    gfx = data.get("Graphics", data)

    # Resolution
    fw = gfx.get("FullscreenWidth", gfx.get("WindowWidth"))
    fh = gfx.get("FullscreenHeight", gfx.get("WindowHeight"))
    if fw is not None and fh is not None:
        r[RESOLUTION] = f"{fw}x{fh}"

    # Screen Mode
    fs = gfx.get("Fullscreen")
    efs = gfx.get("ExclusiveFullscreen")
    if fs is not None:
        if fs == 1:
            r[SCREEN_MODE] = "Exclusive Fullscreen" if efs == 1 else "Borderless Fullscreen"
        else:
            r[SCREEN_MODE] = "Windowed"

    # VSync
    vs = gfx.get("VSync")
    if vs is not None:
        r[VSYNC] = "On" if vs != 0 else "Off"

    # Frame Limit – HZD has DynamicResolutionTargetFPS, SOTR has ForceHalfRefreshRate
    drt = gfx.get("DynamicResolutionTargetFPS")
    fhr = gfx.get("ForceHalfRefreshRate")
    if drt is not None:
        r[FRAME_LIMIT] = f"{drt} FPS" if drt > 0 else "Unlimited"
    elif fhr is not None:
        r[FRAME_LIMIT] = "Half Refresh Rate" if fhr else "Unlimited"

    # Dynamic Resolution
    if drt is not None:
        r[DYNAMIC_RESOLUTION] = f"On (Target: {drt} FPS)" if drt > 0 else "Off"
    else:
        rm = gfx.get("ResolutionModifier")
        if rm is not None:
            pct = rm / 10 if rm > 100 else rm
            r[DYNAMIC_RESOLUTION] = f"{pct:.0f}%" if pct != 100 else "Off (100%)"

    # Upscaling
    um = gfx.get("UpscaleMethod")
    uq = gfx.get("UpscaleQuality")
    dlss = gfx.get("DLSS")
    xess = gfx.get("XESS")
    cas = gfx.get("CAS")
    if um is not None:
        method_map = {0: "Off", 1: "DLSS", 2: "FSR", 3: "CAS", 4: "XeSS"}
        quality_map = {0: "Ultra Performance", 1: "Performance", 2: "Balanced", 3: "Quality", 4: "Ultra Quality"}
        m = method_map.get(um, f"Method {um}")
        q = quality_map.get(uq, "") if uq is not None else ""
        r[UPSCALING] = f"{m} ({q})" if q else m
    elif dlss is not None or xess is not None:
        parts = []
        if xess and xess != 0:
            parts.append("XeSS: On")
        if dlss and dlss != 0:
            parts.append("DLSS: On")
        if cas and cas != 0:
            parts.append("CAS: On")
        r[UPSCALING] = ", ".join(parts) if parts else "Off"

    # Frame Generation
    fg = gfx.get("FrameGen")
    dlssg = gfx.get("DLSSG")
    parts = []
    if fg and fg != 0:
        parts.append("Frame Gen: On")
    if dlssg and dlssg != 0:
        parts.append("DLSS-G: On")
    # If game has RayTracing but no FrameGen keys, it's an older title
    if fg is None and dlssg is None:
        r[FRAME_GENERATION] = "N/A"
    else:
        r[FRAME_GENERATION] = ", ".join(parts) if parts else "Off"

    return r


# ── CS2 (cs2_video.txt + convars) ───────────────────────────────────

def _parse_cs2(all_configs: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """Parse CS2 settings from multiple config file entries."""
    r = _empty_result()

    video_kv: Dict[str, str] = {}
    convar_kv: Dict[str, str] = {}

    for cfg in all_configs:
        content = cfg.get("content") or ""
        path = cfg.get("expanded_path", "")
        if "cs2_video" in path.lower():
            video_kv = _parse_ini_kv(content.replace("\t\t", "=").replace('"', '').replace("\t", ""))
            # Actually parse the Valve KV format properly
            video_kv = {}
            for line in content.splitlines():
                line = line.strip()
                m = re.match(r'"([^"]+)"\s+"([^"]*)"', line)
                if m:
                    video_kv[m.group(1)] = m.group(2)
        elif "machine_convars" in path.lower() or "user_convars" in path.lower():
            for line in content.splitlines():
                line = line.strip()
                m = re.match(r'"([^"]+)"\s+"([^"]*)"', line)
                if m:
                    convar_kv[m.group(1)] = m.group(2)

    # Resolution
    w = video_kv.get("setting.defaultres")
    h = video_kv.get("setting.defaultresheight")
    if w and h:
        r[RESOLUTION] = f"{w}x{h}"

    # Screen Mode
    fs = video_kv.get("setting.fullscreen", "0")
    nwb = video_kv.get("setting.nowindowborder", "0")
    if fs == "1":
        r[SCREEN_MODE] = "Fullscreen"
    elif nwb == "1":
        r[SCREEN_MODE] = "Borderless Windowed"
    else:
        r[SCREEN_MODE] = "Windowed"

    # VSync
    vs = video_kv.get("setting.mat_vsync")
    if vs is not None:
        r[VSYNC] = "On" if vs != "0" else "Off"

    # Frame Limit
    fps = convar_kv.get("fps_max")
    if fps:
        try:
            val = float(fps)
            r[FRAME_LIMIT] = "Unlimited" if val <= 0 else f"{val:.0f} FPS"
        except ValueError:
            r[FRAME_LIMIT] = fps

    # Upscaling
    fsr = video_kv.get("setting.videocfg_fsr_detail")
    if fsr is not None:
        fsr_map = {"0": "Off", "1": "Ultra Quality", "2": "Quality", "3": "Balanced", "4": "Performance"}
        r[UPSCALING] = f"FSR ({fsr_map.get(fsr, fsr)})" if fsr != "0" else "Off"

    # CS2 has no Dynamic Resolution or Frame Generation
    r[DYNAMIC_RESOLUTION] = "N/A"
    r[FRAME_GENERATION] = "N/A"

    return r


# ── Main dispatcher ─────────────────────────────────────────────────

def extract_key_settings(
    game_name: str,
    config_files: List[Dict[str, Any]],
) -> Dict[str, Optional[str]]:
    """Extract the 7 key graphics settings from a game's config files.

    Parameters
    ----------
    game_name:
        The name of the game (used to select the appropriate parser).
    config_files:
        The ``config_files`` list from the export JSON, where each entry
        has ``expanded_path``, ``content``, ``found``, ``error``, etc.

    Returns
    -------
    dict
        A dict mapping each of the 7 setting keys to a human-readable
        value string, or ``None`` if not found.
    """
    # Filter to configs that have readable content
    readable = [c for c in config_files if c.get("content") and c.get("found")]
    if not readable:
        return _empty_result()

    name_lower = game_name.lower()

    # Cyberpunk 2077 – JSON-structured config
    if "cyberpunk" in name_lower:
        return _parse_cyberpunk(readable[0]["content"])

    # CS2 – multiple config files, needs special handling
    if "counter-strike" in name_lower or "cs2" in name_lower:
        return _parse_cs2(readable)

    # Forza Horizon – XML format
    if "forza" in name_lower:
        return _parse_forza_xml(readable[0]["content"])

    # Registry-based games (HZD, Shadow of TR)
    for cfg in readable:
        if cfg.get("type") == "registry":
            return _parse_registry_json(cfg["content"], game_hint=name_lower)

    # Unreal Engine INI fallback (ARC Raiders, etc.)
    for cfg in readable:
        content = cfg["content"]
        if "ResolutionSizeX" in content or "FullscreenMode" in content:
            return _parse_unreal_ini(content)

    # Generic fallback: try all parsers and return the one with most results
    best = _empty_result()
    best_count = 0
    for parser in [_parse_unreal_ini, _parse_forza_xml]:
        for cfg in readable:
            try:
                result = parser(cfg["content"])
                count = sum(1 for v in result.values() if v is not None)
                if count > best_count:
                    best = result
                    best_count = count
            except Exception:
                pass
    return best
