"""The API's view of the supervisor (Section 5.2, Supervisor RPC `GET /status`)."""

from __future__ import annotations

import asyncio
import socket

from titan_api.supervisor_client import supervisor_probe
from titan_core.clock import utc_now
from titan_core.config import SupervisorConfig
from titan_core.protocol.system import SupervisorStatus


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def serve_once(status: int, body: bytes, seen: list[bytes]) -> asyncio.Server:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        seen.append(await reader.readuntil(b"\r\n\r\n"))
        writer.write(
            f"HTTP/1.1 {status} X\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body
        )
        await writer.drain()
        writer.close()

    return await asyncio.start_server(handle, "127.0.0.1", 0)


async def test_returns_the_status_with_the_launch_token() -> None:
    expected = SupervisorStatus(started_at=utc_now(), ready=True, services=[], events=[])
    seen: list[bytes] = []
    server = await serve_once(200, expected.model_dump_json().encode(), seen)
    port = int(server.sockets[0].getsockname()[1])
    try:
        status = await supervisor_probe(SupervisorConfig(port=port), "tok")()
    finally:
        server.close()
        await server.wait_closed()
    assert status == expected
    assert b"GET /status " in seen[0]
    assert b"authorization: bearer tok" in seen[0].lower()


async def test_none_when_absent_or_refusing() -> None:
    assert await supervisor_probe(SupervisorConfig(port=free_port()), "tok", timeout_s=0.5)() is None
    server = await serve_once(401, b"{}", [])
    port = int(server.sockets[0].getsockname()[1])
    try:
        assert await supervisor_probe(SupervisorConfig(port=port), "bad")() is None
    finally:
        server.close()
        await server.wait_closed()
