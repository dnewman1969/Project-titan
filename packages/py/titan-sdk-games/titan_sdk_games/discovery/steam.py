from __future__ import annotations

from pathlib import Path

from titan_sdk_games.discovery.base import StoreInstall, StoreScanner
from titan_sdk_games.types import DiscoveryContext
from titan_sdk_games.vdf import parse_vdf, vdf_get_str


class SteamScanner(StoreScanner):
    name = "steam"

    def scan(self, ctx: DiscoveryContext) -> list[StoreInstall]:
        libraries = list(ctx.steam_libraries)
        if not libraries and ctx.platform == "windows":
            steam_path = ctx.env.get("STEAM_PATH")
            if steam_path:
                libraries = [Path(steam_path)]
        out: list[StoreInstall] = []
        for lib in libraries:
            if not lib.is_dir():
                continue
            out.extend(self._scan_library(lib))
            folders_vdf = lib / "steamapps" / "libraryfolders.vdf"
            if folders_vdf.is_file():
                for extra in self._extra_libraries(folders_vdf):
                    if extra.is_dir():
                        out.extend(self._scan_library(extra))
        return out

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
            if isinstance(lib_path, str) and lib_path:
                libs.append(Path(lib_path))
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
        candidates = sorted(install_path.glob("*.exe"))
        if candidates:
            return candidates[0]
        return None
