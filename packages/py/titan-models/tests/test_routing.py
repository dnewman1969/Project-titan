from __future__ import annotations

import pytest

from titan_models.fake import FakeProvider
from titan_models.registry import ModelsRegistry
from titan_models.routing import ModelsYaml, ProviderSpec, load_models_yaml
from titan_models.types import ChatMessage


def test_load_models_yaml_matches_repo() -> None:
    cfg = load_models_yaml()
    assert cfg.profile == "vram_12gb"
    assert "director" in cfg.profiles["vram_12gb"]["roles"]


@pytest.mark.asyncio
async def test_fallback_emits_notice_and_uses_backup_model() -> None:
    notices: list[tuple[str, str]] = []
    primary = FakeProvider(id="primary", models=[])
    backup = FakeProvider(id="backup", models=["tiny"])
    config = ModelsYaml(
        profile="vram_12gb",
        providers={
            "primary": ProviderSpec(kind="fake"),
            "backup": ProviderSpec(kind="fake"),
        },
        profiles={"vram_12gb": {"roles": {"agent": {"provider": "primary", "model": "missing"}}}},
        fallbacks={"default": [{"provider": "backup", "model": "tiny"}]},
    )
    registry = ModelsRegistry(config=config, providers={"primary": primary, "backup": backup})
    registry.on_notice = lambda level, text: notices.append((level, text))
    result = await registry.chat_for_role("agent", [ChatMessage(role="user", content="hi")])
    assert result.model == "tiny"
    assert notices
