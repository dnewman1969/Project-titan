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


def _normalize_windows_path(path: str) -> str:
    norm = path.strip().replace("\\\\", "\\")
    if sys.platform == "win32":
        norm = norm.replace("/", "\\")
    return norm


def _steam_library_root_from_layout(path: Path) -> Path | None:
    """Infer a Steam library root from steamapps/common or a SteamLibrary folder."""
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    if resolved.name.lower() == "common" and resolved.parent.name.lower() == "steamapps":
        return resolved.parent.parent
    if resolved.name.lower() == "steamapps":
        return resolved.parent
    if resolved.name.lower() == "steamlibrary" and (resolved / "steamapps").is_dir():
        return resolved
    return None


def _steam_library_roots_from_vdf(steam_root: Path) -> list[Path]:
    roots: list[Path] = []
    vdf_candidates = [
        steam_root / "steamapps" / "libraryfolders.vdf",
        steam_root / "config" / "libraryfolders.vdf",
    ]
    vdf_path = next((p for p in vdf_candidates if p.is_file()), None)
    if vdf_path is None:
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
            roots.append(Path(_normalize_windows_path(lib_path)))
    return roots


def _expand_steam_libraries_vdf(libs: list[Path]) -> list[Path]:
    """Repeat libraryfolders.vdf expansion until all secondary roots are included."""
    expanded: list[Path] = []
    seen: set[str] = set()
    for lib in libs:
        try:
            key = str(lib.resolve())
        except OSError:
            key = str(lib)
        if key not in seen:
            seen.add(key)
            expanded.append(lib)
    changed = True
    while changed:
        changed = False
        for lib in list(expanded):
            for extra in _steam_library_roots_from_vdf(lib):
                try:
                    key = str(extra.resolve())
                except OSError:
                    key = str(extra)
                if key in seen:
                    continue
                if not extra.is_dir():
                    continue
                seen.add(key)
                expanded.append(extra)
                changed = True
    return expanded


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
    expanded = _expand_steam_libraries_vdf(libs)
    inferred: list[Path] = []
    for candidate in (
        *(Path(f"{letter}:\\SteamLibrary") for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ"),
        *(Path(f"{letter}:\\Steam") for letter in "DEFGHIJKLMNOPQRSTUVWXYZ"),
    ):
        if candidate.is_dir() and candidate not in expanded:
            inferred.append(candidate)
    if inferred:
        expanded = _expand_steam_libraries_vdf(expanded + inferred)
    for extra_root in inferred:
        if extra_root.is_dir() and extra_root not in expanded:
            expanded.append(extra_root)
    for scan_path in _common_extra_paths(expanded):
        root = _steam_library_root_from_layout(scan_path)
        if root is not None and root.is_dir() and root not in expanded:
            expanded.append(root)
    return _expand_steam_libraries_vdf(expanded)


def _default_epic_manifest_dirs(env: dict[str, str]) -> list[Path]:
    dirs: list[Path] = []
    programdata = env.get("PROGRAMDATA") or r"C:\ProgramData"
    dirs.append(Path(programdata) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests")
    localappdata = env.get("LOCALAPPDATA")
    if localappdata:
        alt = Path(localappdata) / "EpicGamesLauncher" / "Data" / "Manifests"
        if alt not in dirs:
            dirs.append(alt)
    for candidate in (
        Path(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests"),
        Path(r"C:\Program Files\Epic Games"),
    ):
        if candidate not in dirs:
            dirs.append(candidate)
    return dirs


def _gog_default_pack_path() -> Path | None:
    if os.name != "nt":
        return None
    try:
        import winreg

        with winreg.OpenKey(  # type: ignore[attr-defined]
            winreg.HKEY_LOCAL_MACHINE,  # type: ignore[attr-defined]
            r"SOFTWARE\WOW6432Node\GOG.com",
        ) as key:
            raw, _ = winreg.QueryValueEx(key, "DefaultPackPath")  # type: ignore[attr-defined]
        if isinstance(raw, str) and raw.strip():
            return Path(raw.strip().replace("/", "\\"))
    except OSError:
        return None
    return None


def _default_gog_roots() -> list[Path]:
    roots: list[Path] = []
    pack = _gog_default_pack_path()
    if pack is not None and pack.is_dir():
        roots.append(pack)
    for candidate in (
        Path(r"C:\Program Files (x86)\GOG Galaxy\Games"),
        Path(r"C:\Program Files\GOG Galaxy\Games"),
        Path(r"C:\GOG Games"),
        Path(r"D:\GOG Games"),
        Path(r"E:\GOG Games"),
    ):
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    try:
        from titan_sdk_games.discovery.gog_registry import list_gog_registry_installs

        for reg in list_gog_registry_installs():
            parent = reg.install_path.parent
            if parent.is_dir() and parent not in roots:
                roots.append(parent)
            if reg.install_path.is_dir() and reg.install_path not in roots:
                roots.append(reg.install_path)
    except OSError:
        pass
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
