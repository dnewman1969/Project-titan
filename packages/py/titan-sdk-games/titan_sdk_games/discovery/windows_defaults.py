"""Default DiscoveryContext fields on Windows (Steam registry, common library roots)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from titan_sdk_games.types import DiscoveryContext
from titan_sdk_games.vdf import parse_vdf


def _read_registry_string(hive: int, subkey: str, value_name: str) -> str | None:
    try:
        import winreg

        with winreg.OpenKey(hive, subkey) as key:  # type: ignore[attr-defined]
            raw, _ = winreg.QueryValueEx(key, value_name)  # type: ignore[attr-defined]
    except OSError:
        return None
    if isinstance(raw, str) and raw.strip():
        return raw.strip().replace("/", "\\")
    return None


def _steam_registry_candidates() -> list[str]:
    if os.name != "nt":
        return []
    import winreg

    specs: list[tuple[int, str, str]] = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),  # type: ignore[attr-defined]
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "InstallPath"),  # type: ignore[attr-defined]
        (
            winreg.HKEY_LOCAL_MACHINE,  # type: ignore[attr-defined]
            r"SOFTWARE\WOW6432Node\Valve\Steam",
            "InstallPath",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,  # type: ignore[attr-defined]
            r"SOFTWARE\WOW6432Node\Valve\Steam",
            "SteamPath",
        ),
    ]
    found: list[str] = []
    seen: set[str] = set()
    for hive, subkey, value in specs:
        raw = _read_registry_string(hive, subkey, value)
        if not raw:
            continue
        norm = raw.replace("/", "\\")
        if norm not in seen:
            seen.add(norm)
            found.append(norm)
    return found


def _steam_path_from_registry() -> str | None:
    candidates = _steam_registry_candidates()
    return candidates[0] if candidates else None


def _steam_library_roots_from_vdf(steam_root: Path) -> list[Path]:
    roots: list[Path] = []
    vdf_path = steam_root / "steamapps" / "libraryfolders.vdf"
    if not vdf_path.is_file():
        return roots
    try:
        text = vdf_path.read_text(encoding="utf-8", errors="replace")
        parsed = parse_vdf(text)
    except OSError:
        return roots
    libraries = parsed.get("libraryfolders", parsed)
    if not isinstance(libraries, dict):
        return roots
    for entry in libraries.values():
        if not isinstance(entry, dict):
            continue
        lib_path = entry.get("path") or entry.get("Path")
        if isinstance(lib_path, str) and lib_path.strip():
            norm = lib_path.strip().replace("\\\\", "\\")
            if sys.platform == "win32":
                norm = norm.replace("/", "\\")
            roots.append(Path(norm))
    return roots


def _default_steam_libraries(env: dict[str, str]) -> list[Path]:
    libs: list[Path] = []
    steam_candidates: list[str] = []
    if env.get("STEAM_PATH"):
        steam_candidates.append(env["STEAM_PATH"])
    for reg in _steam_registry_candidates():
        if reg not in steam_candidates:
            steam_candidates.append(reg)
    if not steam_candidates:
        fallback = _steam_path_from_registry()
        if fallback:
            steam_candidates.append(fallback)
    for steam in steam_candidates:
        libs.append(Path(steam))
    for candidate in (
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
    ):
        if candidate.is_dir() and candidate not in libs:
            libs.append(candidate)
    expanded: list[Path] = []
    for lib in libs:
        if lib not in expanded:
            expanded.append(lib)
        for extra in _steam_library_roots_from_vdf(lib):
            if extra.is_dir() and extra not in expanded:
                expanded.append(extra)
    return expanded


def _default_epic_manifest_dirs(env: dict[str, str]) -> list[Path]:
    programdata = env.get("PROGRAMDATA") or r"C:\ProgramData"
    return [Path(programdata) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"]


def _default_gog_roots() -> list[Path]:
    roots: list[Path] = []
    for candidate in (
        Path(r"C:\Program Files (x86)\GOG Galaxy\Games"),
        Path(r"C:\GOG Games"),
        Path(r"D:\GOG Games"),
    ):
        if candidate.is_dir():
            roots.append(candidate)
    return roots


def _common_extra_paths(steam_libs: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for lib in steam_libs:
        common = lib / "steamapps" / "common"
        if common.is_dir():
            paths.append(common)
    for candidate in (
        Path(r"C:\Program Files (x86)\Steam\steamapps\common"),
        Path(r"C:\Program Files\Steam\steamapps\common"),
        *(Path(f"{letter}:\\SteamLibrary\\steamapps\\common") for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ"),
    ):
        if candidate.is_dir() and candidate not in paths:
            paths.append(candidate)
    return paths


def enrich_discovery_context(
    *,
    platform: str,
    extra_paths: list[Path] | None = None,
    env: dict[str, str] | None = None,
) -> DiscoveryContext:
    """Merge OS defaults into a DiscoveryContext (safe on non-Windows)."""
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    steam_libs: list[Path] = []
    epic_dirs: list[Path] = []
    gog_roots: list[Path] = []
    scan_extra: list[Path] = list(extra_paths or [])
    if platform == "windows":
        if not merged_env.get("STEAM_PATH"):
            reg_steam = _steam_path_from_registry()
            if reg_steam:
                merged_env["STEAM_PATH"] = reg_steam
        steam_libs = _default_steam_libraries(merged_env)
        epic_dirs = _default_epic_manifest_dirs(merged_env)
        gog_roots = _default_gog_roots()
        for p in _common_extra_paths(steam_libs):
            if p not in scan_extra:
                scan_extra.append(p)
    return DiscoveryContext(
        platform=platform,  # type: ignore[arg-type]
        steam_libraries=steam_libs,
        epic_manifest_dirs=epic_dirs,
        gog_install_roots=gog_roots,
        extra_paths=scan_extra,
        env=merged_env,
    )
