"""Shipped config files parse and stay consistent with each other and with TitanConfig."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from titan_core.config import load_config

CONFIG = Path(__file__).resolve().parents[2] / "config"


def _yaml(name: str) -> Any:
    return yaml.safe_load((CONFIG / name).read_text(encoding="utf-8"))


def test_titan_yaml_loads_into_typed_config() -> None:
    cfg = load_config(app_config_dir=CONFIG, user_config=False)
    assert cfg.api.host == "127.0.0.1"
    assert all(value is False for value in cfg.features.model_dump().values())


def test_models_yaml_roles_reference_known_providers() -> None:
    models = _yaml("models.yaml")
    providers = set(models["providers"])
    assert models["profile"] in models["profiles"]
    for profile in models["profiles"].values():
        for role in profile["roles"].values():
            assert role["provider"] in providers
    for chain in models["fallbacks"].values():
        assert all(step["provider"] in providers for step in chain)


def test_recording_default_preset_exists() -> None:
    cfg = load_config(app_config_dir=CONFIG, user_config=False)
    assert cfg.recording.default_preset in _yaml("recording.yaml")["presets"]


def test_safety_hotkey_matches_titan_yaml() -> None:
    cfg = load_config(app_config_dir=CONFIG, user_config=False)
    assert _yaml("safety.yaml")["kill_switch"]["hotkey"] == cfg.safety.kill_hotkey


def test_egress_allowlist_is_minimal() -> None:
    domains = {entry["domain"] for entry in _yaml("egress.yaml")["allowlist"]}
    assert domains == {"registry.ollama.ai", "huggingface.co"}


def test_titan_yaml_matches_spec_excerpt() -> None:
    spec = (CONFIG.parent / "docs" / "titan-architecture-spec.md").read_text(encoding="utf-8")
    marker = "Excerpt of `config/titan.yaml`:\n```yaml\n"
    start = spec.index(marker) + len(marker)
    excerpt = yaml.safe_load(spec[start : spec.index("```", start)])
    assert excerpt == _yaml("titan.yaml")
