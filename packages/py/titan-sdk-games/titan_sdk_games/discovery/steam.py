from __future__ import annotations

from pathlib import Path

from titan_sdk_games.discovery.base import StoreInstall, StoreScanner
from titan_sdk_games.types import DiscoveryContext
from titan_sdk_games.vdf import parse_vdf, vdf_get_str


class SteamScanner(StoreScanner):
    name = "steam"

    def scan(self, ctx: DiscoveryContext) -> list[StoreInstall]:
        libraries = self._collect_library_roots(ctx)
        out: list[StoreInstall] = []
        seen_libs: set[str] = set()
        for lib in libraries:
            if not lib.is_dir():
                continue
            try:
                key = str(lib.resolve())
            except OSError:
                key = str(lib)
            if key in seen_libs:
                continue
            seen_libs.add(key)
            out.extend(self._scan_library(lib))
        return out

    def _collect_library_roots(self, ctx: DiscoveryContext) -> list[Path]:
        """Steam install root plus every path from libraryfolders.vdf (multi-library)."""
        roots: list[Path] = []
        seen: set[str] = set()

        def add(raw: Path) -> None:
            if not raw:
                return
            try:
                resolved = str(raw.resolve())
            except OSError:
                resolved = str(raw)
            if resolved in seen:
                return
            seen.add(resolved)
            roots.append(raw)

        for lib in ctx.steam_libraries:
            add(lib)
        for raw in ctx.extra_paths:
            root = _steam_library_root_from_common(raw)
            if root is not None:
                add(root)
        if not roots and ctx.platform == "windows":
            steam_path = ctx.env.get("STEAM_PATH")
            if steam_path:
                add(Path(steam_path))

        idx = 0
        while idx < len(roots):
            lib = roots[idx]
            idx += 1
            folders_vdf = lib / "steamapps" / "libraryfolders.vdf"
            if not folders_vdf.is_file():
                alt = lib / "config" / "libraryfolders.vdf"
                folders_vdf = alt if alt.is_file() else folders_vdf
            if not folders_vdf.is_file():
                continue
            for extra in self._extra_libraries(folders_vdf):
                add(extra)
        return roots

    def _extra_libraries(self, path: Path) -> list[Path]:
        text = path.read_text(encoding="utf-8", errors="replace")
        root = parse_vdf(text)
        libs: list[Path] = []
        libraries = root.get("libraryfolders", root)
        if not isinstance(libraries, dict):
            return libs
        for entry in libraries.values():
            if not isinstance(entry, dict):
                continue
            lib_path = entry.get("path") or entry.get("Path")
            if isinstance(lib_path, str) and lib_path.strip():
                libs.append(Path(_normalize_steam_path(lib_path)))
        return libs

    def _scan_library(self, library: Path) -> list[StoreInstall]:
        steamapps = library / "steamapps"
        if not steamapps.is_dir():
            return []
        installs: list[StoreInstall] = []
        for manifest in sorted(steamapps.glob("appmanifest_*.acf")):
            inst = self._read_manifest(manifest)
            if inst is not None:
                installs.append(inst)
        return installs

    def _read_manifest(self, path: Path) -> StoreInstall | None:
        text = path.read_text(encoding="utf-8", errors="replace")
        root = parse_vdf(text)
        app_state = root.get("AppState", root)
        if not isinstance(app_state, dict):
            return None
        fallback_id = path.stem.removeprefix("appmanifest_").removesuffix(".acf")
        app_id = vdf_get_str(app_state, "appid") or fallback_id
        name = vdf_get_str(app_state, "name")
        installdir = vdf_get_str(app_state, "installdir")
        build_id = vdf_get_str(app_state, "buildid")
        if not installdir:
            return None
        library = path.parent.parent
        install_path = (library / "common" / installdir).resolve()
        if not install_path.is_dir():
            install_path = (path.parent / "common" / installdir).resolve()
        exe = self._guess_executable(install_path)
        return StoreInstall(
            store="steam",
            install_path=str(install_path),
            executable_path=str(exe) if exe else str(install_path),
            app_id=app_id,
            build_id=build_id,
            name=name,
        )

    def _guess_executable(self, install_path: Path) -> Path | None:
        for preferred in ("KSP_x64.exe", "KSP.exe", "eurotrucks2.exe", "amtrucks.exe"):
            hit = install_path / preferred
            if hit.is_file():
                return hit
        nested = install_path / "bin" / "win_x64"
        if nested.is_dir():
            for preferred in ("eurotrucks2.exe", "amtrucks.exe"):
                hit = nested / preferred
                if hit.is_file():
                    return hit
        candidates = sorted(install_path.glob("*.exe"))
        if candidates:
            return candidates[0]
        return None


def _normalize_steam_path(path: str) -> str:
    trimmed = path.strip().replace("\\\\", "\\")
    if "\\" in trimmed or (len(trimmed) > 1 and trimmed[1] == ":"):
        return trimmed.replace("/", "\\")
    return trimmed


def _steam_library_root_from_common(path: Path) -> Path | None:
    if path.name.lower() == "common" and path.parent.name.lower() == "steamapps":
        return path.parent.parent
    return None
