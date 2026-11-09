"""Provider registry, role resolution and fallbacks (Section 2.9.2)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from titan_models.fake import FakeProvider
from titan_models.ollama import OllamaProvider
from titan_models.openai_compat import OpenAICompatProvider
from titan_models.protocol import ModelProvider
from titan_models.routing import (
    FallbackRoute,
    ModelsYaml,
    RoleRoute,
    load_models_yaml,
    resolve_profile_roles,
    save_models_yaml,
)
from titan_models.types import ChatMessage, ChatResult, GenerationParams

NoticeCallback = Callable[[str, str], None]


@dataclass
class ModelsRegistry:
    config: ModelsYaml
    providers: dict[str, ModelProvider] = field(default_factory=dict)
    on_notice: NoticeCallback | None = None

    @classmethod
    def from_yaml(cls, path: Path | None = None) -> ModelsRegistry:
        config = load_models_yaml(path)
        providers: dict[str, ModelProvider] = {}
        for name, spec in config.providers.items():
            if spec.kind == "ollama":
                url = spec.base_url or "http://127.0.0.1:11434"
                providers[name] = OllamaProvider(url)
            elif spec.kind in {"openai_compat", "openai-compatible"}:
                url = spec.base_url or "http://127.0.0.1:8080"
                providers[name] = OpenAICompatProvider(f"openai_compat:{name}", url)
            elif spec.kind == "fake":
                providers[name] = FakeProvider(id=name)
        return cls(config=config, providers=providers)

    def roles(self) -> dict[str, RoleRoute]:
        return resolve_profile_roles(self.config)

    def set_profile(self, profile: str) -> None:
        self.config.profile = profile

    def update_roles(self, roles: dict[str, RoleRoute]) -> None:
        profile = self.config.profile
        self.config.profiles.setdefault(profile, {})
        profile_entry = self.config.profiles[profile]
        profile_entry["roles"] = {
            name: {
                "provider": route.provider,
                "model": route.model,
                **({"params": route.params.model_dump(exclude_none=True)} if route.params else {}),
                **({"device": route.device} if route.device else {}),
            }
            for name, route in roles.items()
        }

    def fallbacks(self, key: str = "default") -> list[FallbackRoute]:
        return list(self.config.fallbacks.get(key, []))

    def provider_for(self, provider_id: str) -> ModelProvider:
        if provider_id not in self.providers:
            raise KeyError(f"unknown provider {provider_id!r}")
        return self.providers[provider_id]

    async def model_installed(self, provider_id: str, model: str) -> bool:
        provider = self.provider_for(provider_id)
        try:
            models = await provider.list_models()
        except Exception:
            return False
        return model in models

    async def validate_roles(self, roles: dict[str, RoleRoute]) -> list[str]:
        errors: list[str] = []
        for role, route in roles.items():
            if route.provider not in self.providers:
                errors.append(f"{role}: unknown provider {route.provider!r}")
                continue
            if not await self.model_installed(route.provider, route.model):
                errors.append(f"{role}: model {route.model!r} is not installed for {route.provider}")
        return errors

    async def chat_for_role(
        self,
        role: str,
        messages: list[ChatMessage],
        params: GenerationParams | None = None,
    ) -> ChatResult:
        route = self.roles().get(role)
        if route is None:
            raise KeyError(f"unknown model role {role!r}")
        merged = (
            route.params
            if params is None
            else route.params.model_copy(update=params.model_dump(exclude_none=True))
        )
        return await self._chat_with_fallback(route.provider, route.model, messages, merged)

    async def _chat_with_fallback(
        self,
        provider_id: str,
        model: str,
        messages: list[ChatMessage],
        params: GenerationParams,
    ) -> ChatResult:
        try:
            provider = self.provider_for(provider_id)
            if not await provider.health():
                raise RuntimeError("provider unhealthy")
            if not await self.model_installed(provider_id, model):
                raise RuntimeError("model missing")
            return await provider.chat(model, messages, params)
        except Exception:
            for fb in self.fallbacks():
                try:
                    fb_provider = self.provider_for(fb.provider)
                    if not await fb_provider.health():
                        continue
                    if not await self.model_installed(fb.provider, fb.model):
                        continue
                    self._emit_notice(
                        "warning",
                        f"Falling back to {fb.provider}/{fb.model} for {provider_id}/{model}.",
                    )
                    return await fb_provider.chat(fb.model, messages, params)
                except Exception:  # noqa: S112
                    continue
            raise

    def _emit_notice(self, level: str, text: str) -> None:
        if self.on_notice is not None:
            self.on_notice(level, text)

    def persist(self, path: Path | None = None) -> None:
        save_models_yaml(self.config, path)

    async def list_provider_status(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for provider_id, provider in self.providers.items():
            healthy = await provider.health()
            model_rows: list[dict[str, Any]] = []
            if healthy:
                if isinstance(provider, OllamaProvider):
                    loaded = await provider.loaded_models()
                    for row in await provider.list_models_detail():
                        name = str(row.get("name") or "")
                        size_bytes = row.get("size")
                        size_mb = int(size_bytes // 2**20) if isinstance(size_bytes, int) else None
                        model_rows.append(
                            {
                                "name": name,
                                "size_mb": size_mb,
                                "loaded": name in loaded,
                            }
                        )
                else:
                    for name in await provider.list_models():
                        model_rows.append({"name": name, "size_mb": None, "loaded": False})
            items.append({"id": provider_id, "healthy": healthy, "models": model_rows})
        return items
