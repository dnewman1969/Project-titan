"""Load `config/models.yaml` and resolve role routes (Section 2.9.2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from titan_core.config import find_app_config_dir
from titan_models.types import GenerationParams


class ProviderSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    base_url: str | None = None
    device: str | None = None


class RoleRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    params: GenerationParams = Field(default_factory=GenerationParams)
    device: str | None = None


class FallbackRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    device: str | None = None


class ModelsYaml(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str = "vram_12gb"
    providers: dict[str, ProviderSpec] = Field(default_factory=dict)
    profiles: dict[str, dict[str, Any]] = Field(default_factory=dict)
    fallbacks: dict[str, list[FallbackRoute]] = Field(default_factory=dict)


def load_models_yaml(path: Path | None = None) -> ModelsYaml:
    config_path = path if path is not None else find_app_config_dir() / "models.yaml"
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{config_path}: top level must be a mapping")
    # Parse fallbacks manually because yaml uses shorthand dicts
    fallbacks_raw = raw.get("fallbacks") or {}
    fallbacks: dict[str, list[FallbackRoute]] = {}
    for key, items in fallbacks_raw.items():
        if not isinstance(items, list):
            continue
        fallbacks[str(key)] = [FallbackRoute.model_validate(item) for item in items if isinstance(item, dict)]
    providers_raw = raw.get("providers") or {}
    providers = {
        str(k): ProviderSpec.model_validate(v) for k, v in providers_raw.items() if isinstance(v, dict)
    }
    return ModelsYaml(
        profile=str(raw.get("profile") or "vram_12gb"),
        providers=providers,
        profiles={str(k): v for k, v in (raw.get("profiles") or {}).items() if isinstance(v, dict)},
        fallbacks=fallbacks,
    )


def _coerce_role(entry: dict[str, Any]) -> RoleRoute:
    params_raw = entry.get("params") or {}
    if isinstance(params_raw, dict):
        params = GenerationParams.model_validate(params_raw)
    else:
        params = GenerationParams()
    return RoleRoute(
        provider=str(entry["provider"]),
        model=str(entry["model"]),
        params=params,
        device=entry.get("device"),
    )


def resolve_profile_roles(config: ModelsYaml, profile: str | None = None) -> dict[str, RoleRoute]:
    """Merge `vram_12gb` base roles with the active profile overrides."""
    active = profile or config.profile
    base_roles: dict[str, RoleRoute] = {}
    base = config.profiles.get("vram_12gb", {})
    roles = base.get("roles") if isinstance(base, dict) else None
    if isinstance(roles, dict):
        for name, spec in roles.items():
            if isinstance(spec, dict):
                base_roles[str(name)] = _coerce_role(spec)
    if active != "vram_12gb":
        overlay = config.profiles.get(active, {})
        overlay_roles = overlay.get("roles") if isinstance(overlay, dict) else None
        if isinstance(overlay_roles, dict):
            for name, spec in overlay_roles.items():
                if isinstance(spec, dict):
                    base_roles[str(name)] = _coerce_role(spec)
    return base_roles


def save_models_yaml(config: ModelsYaml, path: Path | None = None) -> None:
    config_path = path if path is not None else find_app_config_dir() / "models.yaml"
    payload: dict[str, Any] = {
        "profile": config.profile,
        "providers": {k: v.model_dump(exclude_none=True) for k, v in config.providers.items()},
        "profiles": config.profiles,
        "fallbacks": {
            key: [route.model_dump(exclude_none=True) for route in routes]
            for key, routes in config.fallbacks.items()
        },
    }
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
