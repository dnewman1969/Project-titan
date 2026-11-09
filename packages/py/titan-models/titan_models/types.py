"""Model-provider value types (Section 2.9.1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_call_id: str | None = None


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str
    parameters: dict[str, Any]


class GenerationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 256
    stop: list[str] = Field(default_factory=list)
    seed: int | None = None
    json_schema: dict[str, Any] | None = None
    tools: list[ToolSpec] = Field(default_factory=list)
    keep_alive: str | None = None


class ChatResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    tool_calls: list[dict[str, Any]]
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    ttft_ms: int
    latency_ms: int
    finish_reason: Literal["stop", "length", "tool", "error", "cancelled"]


class ModelCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    context_tokens: int
    supports_tools: bool
    supports_json_schema: bool
    supports_vision: bool
    est_vram_mb: int
    device: Literal["gpu", "cpu", "mixed"]
