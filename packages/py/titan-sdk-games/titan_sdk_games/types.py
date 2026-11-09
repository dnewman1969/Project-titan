"""Shared DTOs for discovery, integration, and controls."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Consent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    granted: bool


class ControlBindingDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    action_label: str
    context: str = "default"
    device: Literal["keyboard", "mouse", "gamepad", "joystick", "hotas", "wheel", "api"]
    binding: dict[str, Any]
    action_class: Literal["continuous", "discrete", "irreversible", "menu"]
    source: Literal["default", "config_file", "research", "user"] = "config_file"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class IntegrationStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["missing", "outdated", "installed", "failed"]
    details: dict[str, Any] = Field(default_factory=dict)
    instructions_md: str = ""


class DetectedInstall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_slug: str
    store: Literal["steam", "epic", "gog", "standalone"]
    install_path: str
    executable_path: str
    game_version: str | None = None
    build_id: str | None = None
    launch_uri: str | None = None


@dataclass
class DiscoveryContext:
    """Inputs for store scanners and adapter.detect (Section 2.10)."""

    platform: Literal["windows", "linux", "darwin"] = "linux"
    steam_libraries: list[Path] = field(default_factory=list)
    epic_manifest_dirs: list[Path] = field(default_factory=list)
    gog_install_roots: list[Path] = field(default_factory=list)
    extra_paths: list[Path] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
