from __future__ import annotations

import json
import os
from pathlib import Path

from titan_sdk_games.discovery.base import StoreInstall, StoreScanner
from titan_sdk_games.types import DiscoveryContext


class EpicScanner(StoreScanner):
    name = "epic"

    def scan(self, ctx: DiscoveryContext) -> list[StoreInstall]:
        if ctx.platform != "windows":
            return []
        roots = list(ctx.epic_manifest_dirs)
        if not roots:
            programdata = ctx.env.get("PROGRAMDATA")
            if programdata:
                roots = [Path(programdata) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"]
        out: list[StoreInstall] = []
        seen_installs: set[str] = set()
        for root in roots:
            if not root.is_dir():
                continue
            for item in sorted(root.glob("*.item")):
                parsed = self._read_item(item)
                if parsed is None:
                    continue
                key = parsed.install_path.lower()
                if key in seen_installs:
                    continue
                seen_installs.add(key)
                out.append(parsed)
        return out

    def _read_item(self, path: Path) -> StoreInstall | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        if data.get("bIsIncompleteInstall") is True:
            return None
        catalog_id = data.get("CatalogItemId")
        app_name = data.get("AppName")
        app_id = str(catalog_id or app_name or path.stem)
        install = data.get("InstallLocation")
        if not isinstance(install, str) or not install:
            return None
        install_text = str(install)
        install_path = Path(install_text.replace("/", "\\") if os.name == "nt" else install_text)
        if not install_path.is_dir():
            return None
        exe = data.get("LaunchExecutable")
        executable = install_path / exe if isinstance(exe, str) and exe else install_path
        if isinstance(exe, str) and exe:
            exe_path = install_path / exe
            if not exe_path.is_file():
                alt = install_path / Path(exe).name
                executable = alt if alt.is_file() else install_path
        version = data.get("AppVersionString")
        build_id = str(version) if version is not None else None
        return StoreInstall(
            store="epic",
            install_path=str(install_path.resolve()),
            executable_path=str(executable.resolve()),
            app_id=app_id,
            build_id=build_id,
            name=str(data.get("DisplayName") or app_name or app_id),
        )
