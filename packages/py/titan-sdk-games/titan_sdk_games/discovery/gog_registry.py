"""GOG Galaxy install paths from the Windows registry (HKLM\\...\\GOG.com\\Games)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _registry_path(raw: str) -> Path:
    trimmed = raw.strip()
    if len(trimmed) > 1 and trimmed[1] == ":":
        return Path(trimmed.replace("/", "\\"))
    return Path(trimmed)


@dataclass(frozen=True)
class GogRegistryInstall:
    product_id: str
    install_path: Path
    executable_path: Path | None
    game_name: str | None
    build_id: str | None


def _query_gog_value(key, name: str) -> str | None:  # noqa: ANN001
    try:
        import winreg

        raw, _ = winreg.QueryValueEx(key, name)  # type: ignore[attr-defined]
    except OSError:
        return None
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def list_gog_registry_installs() -> list[GogRegistryInstall]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []

    games_key = r"SOFTWARE\WOW6432Node\GOG.com\Games"
    found: list[GogRegistryInstall] = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, games_key) as parent:  # type: ignore[attr-defined]
            count = winreg.QueryInfoKey(parent)[0]  # type: ignore[attr-defined]
            product_ids: list[str] = []
            for i in range(count):
                product_id = winreg.EnumKey(parent, i)  # type: ignore[attr-defined]
                if product_id.isdigit():
                    product_ids.append(product_id)
    except OSError:
        return []

    for product_id in product_ids:
        sub = f"{games_key}\\{product_id}"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub) as key:  # type: ignore[attr-defined]
                path_raw = _query_gog_value(key, "path") or _query_gog_value(key, "PATH")
                if not path_raw:
                    continue
                install_path = _registry_path(path_raw)
                exe_raw = _query_gog_value(key, "exe") or _query_gog_value(key, "EXE")
                exe = _registry_path(exe_raw) if exe_raw else None
                if exe is not None and not exe.is_file():
                    exe_file = _query_gog_value(key, "exeFile") or _query_gog_value(key, "EXEFILE")
                    if exe_file:
                        candidate = install_path / exe_file
                        exe = candidate if candidate.is_file() else exe
                name = _query_gog_value(key, "gameName") or _query_gog_value(key, "GAMENAME")
                build = _query_gog_value(key, "BUILDID") or _query_gog_value(key, "BUILD") or _query_gog_value(key, "ver")
                found.append(
                    GogRegistryInstall(
                        product_id=product_id,
                        install_path=install_path,
                        executable_path=exe,
                        game_name=name,
                        build_id=build,
                    )
                )
        except OSError:
            continue
    return found
