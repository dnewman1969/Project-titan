"""Embedding helpers (Section 2.9.1)."""

from __future__ import annotations

from typing import Protocol


class Embedder(Protocol):
    model: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbedder:
    model = "fake-embed"
    dim = 3

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 0.25, 0.5] for text in texts]


def sentence_transformers_embedder(model_name: str, *, device: str = "cpu") -> Embedder:
    from sentence_transformers import SentenceTransformer

    class _ST:
        def __init__(self) -> None:
            self._model = SentenceTransformer(model_name, device=device)
            self.model = model_name
            self.dim = int(self._model.get_sentence_embedding_dimension())

        def embed(self, texts: list[str]) -> list[list[float]]:
            vectors = self._model.encode(texts, convert_to_numpy=True)
            return [row.tolist() for row in vectors]

    return _ST()
