"""GOG discovery stub on non-Windows; registry parsing is exercised via fixtures in tests."""

from __future__ import annotations

import json
from pathlib import Path

from titan_sdk_games.discovery.base import StoreInstall, StoreScanner
from titan_sdk_games.types import DiscoveryContext


class GogScanner(StoreScanner):
    name = "gog"

    def scan(self, ctx: DiscoveryContext) -> list[StoreInstall]:
        roots = list(ctx.gog_install_roots)
        out: list[StoreInstall] = []
        for root in roots:
            if not root.is_dir():
                continue
            for manifest in sorted(root.glob("**/*.json")):
                if manifest.name != "goggame.json":
                    continue
                parsed = self._read_goggame(manifest)
                if parsed is not None:
                    out.append(parsed)
        if ctx.platform != "windows" and not roots:
            return []
        return out

    def _read_goggame(self, path: Path) -> StoreInstall | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        product_id = str(data.get("productId") or data.get("gameId") or path.parent.name)
        install_path = path.parent
        exe = data.get("playTasks", [{}])
        executable = install_path
        if isinstance(exe, list) and exe:
            first = exe[0]
            if isinstance(first, dict) and isinstance(first.get("path"), str):
                executable = install_path / first["path"]
        version = data.get("version")
        return StoreInstall(
            store="gog",
            install_path=str(install_path.resolve()),
            executable_path=str(executable.resolve()),
            app_id=product_id,
            build_id=str(version) if version is not None else None,
            name=str(data.get("name") or product_id),
        )
