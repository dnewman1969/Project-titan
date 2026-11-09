"""ModelProvider protocol: Ollama, OpenAI-compatible, SentenceTransformers and Fake (Section 2.9)."""

from titan_models.fake import FakeProvider
from titan_models.llm_scheduler import LlmScheduler
from titan_models.ollama import OllamaProvider
from titan_models.openai_compat import OpenAICompatProvider
from titan_models.registry import ModelsRegistry
from titan_models.resource_guard import ResourceGuard
from titan_models.routing import load_models_yaml
from titan_models.types import (
    ChatMessage,
    ChatResult,
    GenerationParams,
    ModelCapabilities,
    ToolSpec,
)

__all__ = [
    "ChatMessage",
    "ChatResult",
    "FakeProvider",
    "GenerationParams",
    "LlmScheduler",
    "ModelCapabilities",
    "ModelsRegistry",
    "OllamaProvider",
    "OpenAICompatProvider",
    "ResourceGuard",
    "ToolSpec",
    "load_models_yaml",
]
