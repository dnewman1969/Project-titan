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


def test_sample_vessel_reads_flight_and_reports_no_vessel() -> None:
    from titan_game_ksp.vessel_sample import sample_vessel

    class _Flight:
        mean_altitude = 1200.0
        latitude = -0.2
        longitude = -74.0
        speed = 80.0
        vertical_speed = 60.0
        horizontal_speed = 20.0
        g_force = 1.5
        dynamic_pressure = 4000.0
        static_pressure = 10000.0
        atmosphere_density = 0.5
        heading = 90.0
        pitch = 80.0
        roll = 1.0

    class _Body:
        name = "Kerbin"

    class _Orbit:
        apoapsis_altitude = 80000.0
        periapsis_altitude = -400000.0
        inclination = 0.0
        eccentricity = 0.9
        body = _Body()

    class _Control:
        throttle = 0.8
        sas = True
        rcs = False
        current_stage = 2

    class _Situation:
        name = "flying"

    class _Vessel:
        name = "Explorer"
        situation = _Situation()
        surface_reference_frame = "srf"
        control = _Control()
        orbit = _Orbit()

        def flight(self, ref: object = None) -> _Flight:
            assert ref == "srf"
            return _Flight()

    class _Scene:
        name = "flight"

    class _Krpc:
        current_game_scene = _Scene()
        paused = False

    class _Center:
        active_vessel = _Vessel()

    class _Conn:
        space_center = _Center()
        krpc = _Krpc()

    raw = sample_vessel(_Conn())
    assert raw["scene"] == "flight"
    assert raw["vessel_name"] == "Explorer"
    assert raw["mean_altitude_m"] == 1200.0
    assert raw["heading_deg"] == 90.0
    assert raw["apoapsis_altitude_m"] == 80000.0
    assert raw["sas"] is True

    class _SpaceCenterScene:
        name = "space_center"

    class _MenuKrpc:
        current_game_scene = _SpaceCenterScene()
        paused = False

    class _MenuCenter:
        active_vessel = None

    class _Menu:
        space_center = _MenuCenter()
        krpc = _MenuKrpc()

    idle = sample_vessel(_Menu())
    assert idle["scene"] == "space_center"
    assert idle["vessel_present"] is False


@pytest.mark.asyncio
async def test_ksp_adapter_samples_injected_vessel() -> None:
    adapter = KspAdapter(
        sample_fn=lambda: {
            "scene": "flight",
            "paused": False,
            "situation": "flying",
            "vessel_name": "Explorer",
            "mean_altitude_m": 1500.0,
            "latitude_deg": -0.1,
            "longitude_deg": -74.0,
            "heading_deg": 90.0,
            "pitch_deg": 70.0,
            "roll_deg": 0.0,
            "vertical_speed_mps": 40.0,
            "speed_mps": 50.0,
            "apoapsis_altitude_m": 20000.0,
        }
    )
    adapter._connected = True
    frames = adapter.frames()
    raw = await frames.__anext__()
    await frames.aclose()
    frame = adapter.normalize(raw)
    assert frame.scene == "flight"
    assert frame.vehicle.name == "Explorer"
    assert frame.vehicle.attitude is not None
    assert frame.vehicle.attitude.heading_deg == 90.0
    assert frame.vehicle.geo is not None
    assert frame.vehicle.geo.alt_m == 1500.0
    assert frame.vehicle.orbit is not None
    assert frame.vehicle.orbit.apoapsis_m == 20000.0
