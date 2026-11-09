"""In-memory `GameProfile` used by adapters before persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class GameProfile:
    id: UUID | None
    game_id: UUID | None
    store: str
    install_path: str
    executable_path: str
    launch_uri: str | None = None
    launch_args: list[str] = field(default_factory=list)
    game_version: str | None = None
    config_paths: list[dict[str, str]] = field(default_factory=list)
