"""Pydantic models for `titan-game.yaml` (Section 2.10.1)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PluginSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    install_to: str
    sha256: str


class TelemetrySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    requires_plugin: bool = False
    plugin: PluginSpec | None = None
    native_rate_hz: int = Field(default=20, ge=1)


class DetectionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steam_app_ids: list[int] = Field(default_factory=list)
    epic_catalog_ids: list[str] = Field(default_factory=list)
    gog_product_ids: list[str] = Field(default_factory=list)
    executables: list[str] = Field(default_factory=list)
    registry_keys: list[str] = Field(default_factory=list)


class LaunchSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steam_uri: str | None = None
    args: list[str] = Field(default_factory=list)


class CapabilitiesSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telemetry: bool = True
    control: Literal["none", "api", "virtual_gamepad", "keyboard_mouse"] = "none"
    anti_cheat: bool = False
    multiplayer_modes: list[str] = Field(default_factory=list)


class ConfigFileSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    kind: Literal["controls", "graphics", "other"] = "other"
    parser: str | None = None


class GameManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    adapter: str
    adapter_version: str
    domain: Literal[
        "space",
        "ground_vehicle",
        "aircraft",
        "naval",
        "strategy",
        "other",
    ]
    genre: list[str] = Field(default_factory=list)
    detection: DetectionSpec = Field(default_factory=DetectionSpec)
    launch: LaunchSpec = Field(default_factory=LaunchSpec)
    telemetry: TelemetrySpec
    capabilities: CapabilitiesSpec = Field(default_factory=CapabilitiesSpec)
    config_files: list[ConfigFileSpec] = Field(default_factory=list)
    save_files: list[str] = Field(default_factory=list)
    event_rules: str = "events.yaml"
    teams: str = "teams/"
    controls_default: str = "controls_default.yaml"
    fixtures: str = "fixtures/"

    @field_validator("genre", mode="before")
    @classmethod
    def _coerce_genre(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v) for v in value]
        return [str(value)]

    @classmethod
    def from_yaml_path(cls, path: Path) -> GameManifest:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError(f"{path}: expected mapping")
        return cls.model_validate(data)

    def store_ids(self) -> dict[str, list[int] | list[str]]:
        steam: list[int] = list(self.detection.steam_app_ids)
        epic: list[str] = list(self.detection.epic_catalog_ids)
        gog: list[str] = list(self.detection.gog_product_ids)
        return {"steam": steam, "epic": epic, "gog": gog}
