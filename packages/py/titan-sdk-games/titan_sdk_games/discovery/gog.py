"""GOG discovery stub on non-Windows; registry parsing is exercised via fixtures in tests."""

from __future__ import annotations

import json
from pathlib import Path

from titan_sdk_games.discovery.base import StoreInstall, StoreScanner
from titan_sdk_games.discovery.gog_registry import list_gog_registry_installs
from titan_sdk_games.types import DiscoveryContext


def _install_path_str(path: Path) -> str:
    try:
        return str(path.resolve())
    except (NotImplementedError, OSError):
        return str(path)


class GogScanner(StoreScanner):
    name = "gog"

    def scan(self, ctx: DiscoveryContext) -> list[StoreInstall]:
        out: list[StoreInstall] = []
        seen_paths: set[str] = set()

        def add(inst: StoreInstall) -> None:
            key = inst.install_path.lower()
            if key in seen_paths:
                return
            seen_paths.add(key)
            out.append(inst)

        if ctx.platform == "windows":
            for reg in list_gog_registry_installs():
                if not reg.install_path.is_dir():
                    continue
                executable = reg.executable_path
                if executable is None or not executable.is_file():
                    executable = reg.install_path
                add(
                    StoreInstall(
                        store="gog",
                        install_path=_install_path_str(reg.install_path),
                        executable_path=_install_path_str(
                            executable if isinstance(executable, Path) else Path(executable)
                        ),
                        app_id=reg.product_id,
                        build_id=reg.build_id,
                        name=reg.game_name,
                    )
                )

        roots = list(ctx.gog_install_roots)
        for root in roots:
            if not root.is_dir():
                continue
            for manifest in sorted(root.glob("**/*.json")):
                if manifest.name != "goggame.json":
                    continue
                parsed = self._read_goggame(manifest)
                if parsed is not None:
                    add(parsed)
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
