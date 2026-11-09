"""Minimal fake kRPC server for adapter tests (M5.T2)."""

from __future__ import annotations

import asyncio
import json
import struct
from collections.abc import AsyncIterator


class FakeKrpcServer:
    """Accepts length-prefixed JSON RPC messages and returns canned responses."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self._server: asyncio.Server | None = None
        self.scene = "flight"
        self.situation = "pre_launch"
        self._calls = 0

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        sockets = self._server.sockets
        if not sockets:
            raise RuntimeError("server failed to bind")
        self.port = int(sockets[0].getsockname()[1])
        return self.port

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                header = await reader.readexactly(4)
                (length,) = struct.unpack(">I", header)
                body = await reader.readexactly(length)
                self._calls += 1
                _ = json.loads(body.decode("utf-8"))
                reply = {
                    "status": "ok",
                    "scene": self.scene,
                    "situation": self.situation,
                    "calls": self._calls,
                }
                payload = json.dumps(reply).encode("utf-8")
                writer.write(struct.pack(">I", len(payload)) + payload)
                await writer.drain()
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()

    async def stream_frames(self, samples: list[dict[str, object]]) -> AsyncIterator[dict[str, object]]:
        for sample in samples:
            yield sample
            await asyncio.sleep(0.01)
