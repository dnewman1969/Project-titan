"""HTTP Chroma client for loopback Chroma (Section 4.3)."""

from __future__ import annotations

from typing import Any

from titan_core.http import HTTPError, local_client
from titan_memory.collections import COLLECTION_NAMES, collection_metadata


class ChromaVectorStore:
    tenant = "titan"
    database = "default"

    def __init__(self, base_url: str, *, timeout_s: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._prefix = f"/api/v1/tenants/{self.tenant}/databases/{self.database}"

    async def ensure_collection(self, name: str, *, metadata: dict[str, Any] | None = None) -> None:
        meta = metadata or collection_metadata()
        async with local_client(timeout_s=self.timeout_s) as client:
            created = await client.post(
                f"{self.base_url}{self._prefix}/collections",
                json={"name": name, "metadata": meta},
            )
            if created.status_code in {200, 201}:
                return
            if created.status_code == 409:
                return
            created.raise_for_status()

    async def upsert(
        self,
        collection: str,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        embeddings: list[list[float]] | None = None,
    ) -> None:
        coll_id = await self._collection_id(collection)
        payload: dict[str, Any] = {"ids": ids, "documents": documents, "metadatas": metadatas}
        if embeddings is not None:
            payload["embeddings"] = embeddings
        async with local_client(timeout_s=self.timeout_s) as client:
            response = await client.post(
                f"{self.base_url}{self._prefix}/collections/{coll_id}/upsert",
                json=payload,
            )
            response.raise_for_status()

    async def query(
        self,
        collection: str,
        *,
        query_embeddings: list[list[float]],
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        coll_id = await self._collection_id(collection)
        payload: dict[str, Any] = {"query_embeddings": query_embeddings, "n_results": n_results}
        if where is not None:
            payload["where"] = where
        async with local_client(timeout_s=self.timeout_s) as client:
            response = await client.post(
                f"{self.base_url}{self._prefix}/collections/{coll_id}/query",
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        return body if isinstance(body, dict) else {}

    async def delete(self, collection: str, *, ids: list[str]) -> None:
        coll_id = await self._collection_id(collection)
        async with local_client(timeout_s=self.timeout_s) as client:
            response = await client.post(
                f"{self.base_url}{self._prefix}/collections/{coll_id}/delete",
                json={"ids": ids},
            )
            response.raise_for_status()

    async def bootstrap(self) -> None:
        for name in COLLECTION_NAMES:
            await self.ensure_collection(name)

    async def _collection_id(self, name: str) -> str:
        async with local_client(timeout_s=self.timeout_s) as client:
            response = await client.get(f"{self.base_url}{self._prefix}/collections/{name}")
            if response.status_code == 404:
                await self.ensure_collection(name)
                response = await client.get(f"{self.base_url}{self._prefix}/collections/{name}")
            response.raise_for_status()
            body = response.json()
        if not isinstance(body, dict) or not body.get("id"):
            raise HTTPError("collection lookup failed")
        return str(body["id"])
