from __future__ import annotations

from titan_memory.embedder import FakeEmbedder


def test_fake_embedder_vectors() -> None:
    embedder = FakeEmbedder()
    vectors = embedder.embed(["ab", "x"])
    assert len(vectors) == 2
    assert vectors[0][0] == 2.0
    assert embedder.dim == 3
