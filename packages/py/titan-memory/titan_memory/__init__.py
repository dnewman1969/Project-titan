"""VectorStore interface, Chroma implementation, embedder and retrieval scoring (Section 4.3)."""

from titan_memory.chroma_store import ChromaVectorStore
from titan_memory.collections import COLLECTION_NAMES, collection_metadata
from titan_memory.scoring import retrieval_score
from titan_memory.vector_store import VectorStore

__all__ = [
    "COLLECTION_NAMES",
    "ChromaVectorStore",
    "VectorStore",
    "collection_metadata",
    "retrieval_score",
]
