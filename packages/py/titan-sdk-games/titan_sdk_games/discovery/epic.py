from __future__ import annotations

import json
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
        for root in roots:
            if not root.is_dir():
                continue
            for item in sorted(root.glob("*.item")):
                parsed = self._read_item(item)
                if parsed is not None:
                    out.append(parsed)
        return out

    def _read_item(self, path: Path) -> StoreInstall | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        catalog_id = str(data.get("CatalogItemId") or data.get("AppName") or path.stem)
        install = data.get("InstallLocation")
        if not isinstance(install, str) or not install:
            return None
        install_path = Path(install)
        exe = data.get("LaunchExecutable")
        executable = install_path / exe if isinstance(exe, str) and exe else install_path
        version = data.get("AppVersionString")
        build_id = str(version) if version is not None else None
        return StoreInstall(
            store="epic",
            install_path=str(install_path.resolve()),
            executable_path=str(executable.resolve()),
            app_id=catalog_id,
            build_id=build_id,
            name=str(data.get("DisplayName") or catalog_id),
        )
