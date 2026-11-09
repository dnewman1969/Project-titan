from __future__ import annotations

from titan_sdk_games.discovery.base import StoreInstall, StoreScanner
from titan_sdk_games.types import DiscoveryContext


class StandaloneScanner(StoreScanner):
    name = "standalone"

    def scan(self, ctx: DiscoveryContext) -> list[StoreInstall]:
        out: list[StoreInstall] = []
        for raw in ctx.extra_paths:
            path = raw.resolve()
            if path.is_file() and path.suffix.lower() in {".exe", ""}:
                out.append(
                    StoreInstall(
                        store="standalone",
                        install_path=str(path.parent),
                        executable_path=str(path),
                        app_id=path.stem,
                        build_id=None,
                        name=path.stem,
                    )
                )
            elif path.is_dir():
                for exe in sorted(path.glob("**/*.exe")):
                    out.append(
                        StoreInstall(
                            store="standalone",
                            install_path=str(path),
                            executable_path=str(exe.resolve()),
                            app_id=exe.stem,
                            build_id=None,
                            name=exe.stem,
                        )
                    )
        return out
