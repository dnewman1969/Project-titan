from __future__ import annotations

import asyncio
import json
import struct
from pathlib import Path

import pytest
from titan_game_ksp.adapter import KspAdapter
from titan_game_ksp.krpc_fake import FakeKrpcServer

from titan_sdk_games.adapter import AdapterConfig
from titan_sdk_games.profiles import GameProfile


@pytest.mark.asyncio
async def test_fake_krpc_server_responds() -> None:
    server = FakeKrpcServer()
    port = await server.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        payload = json.dumps({"procedure": "Scene"}).encode("utf-8")
        writer.write(struct.pack(">I", len(payload)) + payload)
        await writer.drain()
        header = await reader.readexactly(4)
        (length,) = struct.unpack(">I", header)
        body = json.loads((await reader.readexactly(length)).decode("utf-8"))
        assert body["status"] == "ok"
        writer.close()
        await writer.wait_closed()
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_ksp_adapter_connects_to_fake_server(tmp_path: Path) -> None:
    server = FakeKrpcServer()
    port = await server.start()
    try:
        adapter = KspAdapter()
        profile = GameProfile(
            id=None,
            game_id=None,
            store="standalone",
            install_path=str(tmp_path),
            executable_path=str(tmp_path / "KSP_x64.exe"),
        )
        await adapter.connect(profile, AdapterConfig(krpc_port=port))
        assert adapter._connected
        await adapter.disconnect()
    finally:
        await server.stop()
