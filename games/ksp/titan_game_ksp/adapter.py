from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID

from titan_core.protocol.events import GameEvent
from titan_core.protocol.telemetry import (
    TELEMETRY_SCHEMA,
    Controls,
    Damage,
    Environment,
    Resource,
    Stage,
    TelemetryFrame,
    Vehicle,
    Velocity,
)
from titan_sdk_games.adapter import AdapterConfig, GameAdapter, RawFrame
from titan_sdk_games.exceptions import GameNotConnected
from titan_sdk_games.profiles import GameProfile
from titan_sdk_games.types import Consent, IntegrationStatus

SESSION_STUB = UUID("00000000-0000-0000-0000-000000000001")


class KspAdapter(GameAdapter):
    def __init__(self) -> None:
        self._replay_path: Path | None = None
        self._connected = False
        self._krpc = None

    @classmethod
    def manifest_path(cls) -> Path:
        return Path(__file__).resolve().parent.parent / "titan-game.yaml"

    def check_integration(self, profile: GameProfile) -> IntegrationStatus:
        manifest = self.load_manifest()
        plugin = manifest.telemetry.plugin
        if plugin is None:
            return IntegrationStatus(status="installed")
        target = Path(profile.install_path) / plugin.install_to
        if target.is_dir() and any(target.iterdir()):
            return IntegrationStatus(
                status="installed",
                details={"required": f"{plugin.name} {plugin.version}", "found": "present"},
            )
        return super().check_integration(profile)

    def install_integration(self, profile: GameProfile, consent: Consent) -> IntegrationStatus:
        if not consent.granted:
            return IntegrationStatus(status="failed", details={"reason": "consent_required"})
        before = self.check_integration(profile)
        if before.status == "installed":
            return before
        manifest = self.load_manifest()
        plugin = manifest.telemetry.plugin
        if plugin is None:
            return IntegrationStatus(status="installed")
        target = Path(profile.install_path) / plugin.install_to
        target.mkdir(parents=True, exist_ok=True)
        marker = target / ".titan-krpc-stub"
        marker.write_text("kRPC stub installed for tests\n", encoding="utf-8")
        return self.check_integration(profile)

    async def connect(self, profile: GameProfile, cfg: AdapterConfig) -> None:
        del profile
        replay = cfg.get("replay_path")
        if replay:
            self._replay_path = Path(str(replay))
            self._connected = self._replay_path.is_file()
            return
        address = str(cfg.get("krpc_host", "127.0.0.1"))
        port = int(cfg.get("krpc_port", 50000))
        try:
            reader, writer = await __import__("asyncio").wait_for(
                __import__("asyncio").open_connection(address, port), timeout=0.5
            )
        except (OSError, TimeoutError) as exc:
            raise GameNotConnected(str(exc)) from exc
        writer.close()
        await writer.wait_closed()
        del reader
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False
        self._replay_path = None

    async def frames(self) -> AsyncIterator[RawFrame]:
        if self._replay_path is not None:
            with self._replay_path.open(encoding="utf-8") as fh:
                for line in fh:
                    text = line.strip()
                    if not text:
                        continue
                    data = json.loads(text)
                    if isinstance(data, dict):
                        yield RawFrame(data)
            return
        if not self._connected:
            raise GameNotConnected("not connected")
        while self._connected:
            await __import__("asyncio").sleep(0.05)
            yield RawFrame({"scene": "flight", "paused": False, "t_session_ms": 0, "t_mono_ns": 0})

    def normalize(self, raw: RawFrame) -> TelemetryFrame:
        manifest = self.load_manifest()
        situation = str(raw.get("situation", raw.get("vehicle_situation", "pre_launch")))
        scene = str(raw.get("scene", "flight"))
        resources: list[Resource] = []
        lf_amount = _float(raw.get("liquid_fuel"))
        lf_cap = _float(raw.get("liquid_fuel_cap", 1)) or 1.0
        if lf_amount is not None:
            resources.append(
                Resource(
                    id="LiquidFuel",
                    name="Liquid Fuel",
                    amount=lf_amount,
                    capacity=lf_cap,
                    unit="L",
                    scope="vehicle",
                )
            )
        dyn_p = _float(raw.get("dynamic_pressure_pa"))
        alt = _float(raw.get("mean_altitude_m", raw.get("altitude_m")))
        lat = _float(raw.get("latitude_deg"))
        lon = _float(raw.get("longitude_deg"))
        geo = None
        if lat is not None and lon is not None and alt is not None:
            from titan_core.protocol.telemetry import Geo

            geo = Geo(lat_deg=lat, lon_deg=lon, alt_m=alt)
        vehicle = Vehicle(
            name=raw.get("vessel_name") if isinstance(raw.get("vessel_name"), str) else None,
            kind="rocket",
            position=None,
            geo=geo,
            attitude=None,
            velocity=Velocity(
                speed_mps=_float(raw.get("speed_mps")) or 0.0,
                vertical_mps=_float(raw.get("vertical_speed_mps")),
                horizontal_mps=_float(raw.get("horizontal_speed_mps")),
            ),
            accel_g=_float(raw.get("accel_g")),
            controls=Controls(
                throttle=_float(raw.get("throttle")),
                brake=None,
                steer=None,
                clutch=None,
                gear=None,
                sas=raw.get("sas") if isinstance(raw.get("sas"), bool) else None,
                rcs=raw.get("rcs") if isinstance(raw.get("rcs"), bool) else None,
                parking_brake=None,
                cruise_control_mps=None,
                lights=None,
            ),
            engine=None,
            damage=Damage(overall=None, parts={}),
            situation=situation,
            stage=Stage(
                current=int(raw.get("stage_current", 1)),
                total=int(raw["stage_total"]) if raw.get("stage_total") is not None else None,
                dv_ms=_float(raw.get("stage_dv_ms")),
            ),
            orbit=None,
        )
        return TelemetryFrame(
            schema=TELEMETRY_SCHEMA,
            session_id=SESSION_STUB,
            game=manifest.id,
            adapter_version=manifest.adapter_version,
            seq=int(raw.get("seq", 0)),
            t_mono_ns=int(raw.get("t_mono_ns", 0)),
            t_session_ms=int(raw.get("t_session_ms", 0)),
            t_game_s=_float(raw.get("ut_s")),
            paused=bool(raw.get("paused", False)),
            scene=scene,
            domain=manifest.domain,
            vehicle=vehicle,
            resources=resources,
            environment=Environment(
                body=raw.get("body") if isinstance(raw.get("body"), str) else "Kerbin",
                atmosphere_density=_float(raw.get("atmosphere_density")),
                dynamic_pressure_pa=dyn_p,
                static_pressure_pa=_float(raw.get("static_pressure_pa")),
                speed_limit_mps=None,
                weather=None,
                local_time=None,
            ),
            job=None,
            economy=None,
            game_specific=_game_specific(raw),
        )

    def detect_events(
        self,
        prev: TelemetryFrame | None,
        cur: TelemetryFrame,
        raw: RawFrame,
    ) -> list[GameEvent]:
        del prev, cur
        if raw.get("adapter_event") == "vessel_destroyed":
            return [
                GameEvent(
                    id=__import__("uuid").uuid5(__import__("uuid").NAMESPACE_URL, "ksp-vessel-destroyed"),
                    session_id=SESSION_STUB,
                    seq=0,
                    type="ksp.vessel_destroyed",
                    category="game",
                    severity="critical",
                    salience=1.0,
                    source="adapter:ksp",
                    t_mono_ns=int(raw.get("t_mono_ns", 0)),
                    t_session_ms=int(raw.get("t_session_ms", 0)),
                    occurred_at=__import__("datetime").datetime(
                        2020, 1, 1, tzinfo=__import__("datetime").UTC
                    ),
                    frame_seq=int(raw.get("seq", 0)),
                    payload={},
                )
            ]
        return []

    def launch_stub(self, profile: GameProfile) -> dict[str, str | None]:
        manifest = self.load_manifest()
        return {
            "method": "steam_uri",
            "launch_uri": manifest.launch.steam_uri,
            "executable_path": profile.executable_path,
        }


def _float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _game_specific(raw: RawFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if raw.get("vessel_destroyed"):
        out["vessel_destroyed"] = True
    for key in ("met_s", "ut_s", "vessel_type", "part_count"):
        if key in raw:
            out[key] = raw[key]
    return out
