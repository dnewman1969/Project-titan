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
    Job,
    Resource,
    TelemetryFrame,
    Vehicle,
    Velocity,
)
from titan_game_scs.layout import ScsLayout, layout_path
from titan_game_scs.shm import ScsSharedMemory
from titan_sdk_games.adapter import AdapterConfig, GameAdapter, RawFrame
from titan_sdk_games.exceptions import GameNotConnected
from titan_sdk_games.manifest import GameManifest
from titan_sdk_games.profiles import GameProfile
from titan_sdk_games.types import Consent, IntegrationStatus

SESSION_STUB = UUID("00000000-0000-0000-0000-000000000002")


class ScsAdapter(GameAdapter):
    manifest_root: Path

    def __init__(self) -> None:
        self._replay_path: Path | None = None
        self._shm: ScsSharedMemory | None = None
        self._layout: ScsLayout | None = None
        self._currency = "EUR"
        self._slug = "ets2"

    @classmethod
    def manifest_path(cls) -> Path:
        root = getattr(cls, "manifest_root", None)
        if root is None:
            raise NotImplementedError("ScsAdapter subclass must set manifest_root")
        return root / "titan-game.yaml"

    def check_integration(self, profile: GameProfile) -> IntegrationStatus:
        status = super().check_integration(profile)
        if status.status == "missing":
            plugin_path = Path(profile.install_path) / "bin/win_x64/plugins/scs-telemetry.dll"
            if plugin_path.is_file():
                return IntegrationStatus(
                    status="installed",
                    details={**status.details, "found": "present-unverified"},
                )
        return status

    def install_integration(self, profile: GameProfile, consent: Consent) -> IntegrationStatus:
        if not consent.granted:
            return IntegrationStatus(status="failed", details={"reason": "consent_required"})
        current = self.check_integration(profile)
        if current.status == "installed":
            return current
        target = Path(profile.install_path) / "bin/win_x64/plugins/scs-telemetry.dll"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(b"SCS-TELEMETRY-TEST-STUB")
        return self.check_integration(profile)

    async def connect(self, profile: GameProfile, cfg: AdapterConfig) -> None:
        del profile
        replay = cfg.get("replay_path")
        if replay:
            self._replay_path = Path(str(replay))
            return
        shm_path = cfg.get("shm_file")
        revision = int(cfg.get("plugin_revision", 12))
        try:
            layout = ScsLayout.from_yaml(layout_path(revision))
        except FileNotFoundError as exc:
            raise GameNotConnected(f"unknown layout revision {revision}") from exc
        self._layout = layout
        if shm_path:
            self._shm = ScsSharedMemory(layout, path=Path(str(shm_path)))
        else:
            try:
                self._shm = ScsSharedMemory(layout)
            except OSError as exc:
                raise GameNotConnected(str(exc)) from exc

    async def disconnect(self) -> None:
        if self._shm is not None:
            self._shm.close()
        self._shm = None
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
        if self._shm is None:
            raise GameNotConnected("not connected")
        last_ts = -1
        while True:
            snap = self._shm.snapshot()
            ts = int(snap.get("timestamp", 0))
            if ts != last_ts:
                last_ts = ts
                yield RawFrame(
                    {"scs": snap, "t_mono_ns": ts * 1_000_000, "t_session_ms": ts, "scene": "driving"}
                )
            await __import__("asyncio").sleep(0.05)

    def normalize(self, raw: RawFrame) -> TelemetryFrame:
        manifest = self.load_manifest()
        self._slug = manifest.id
        self._currency = "USD" if manifest.id == "ats" else "EUR"
        data = raw.get("scs") if isinstance(raw.get("scs"), dict) else raw
        fuel = _float(data.get("fuel_l", data.get("fuel")))
        cap = _float(data.get("fuel_capacity_l", data.get("fuel_capacity", 1))) or 1.0
        speed = abs(_float(data.get("speed_mps", data.get("speed"))) or 0.0)
        game_time_min = _float(data.get("game_time_min", data.get("game_time")))
        paused = bool(data.get("paused", raw.get("paused", False)))
        job_active = bool(data.get("job_active", raw.get("job_active", False)))
        resources = [
            Resource(id="fuel", name="Diesel", amount=fuel or 0.0, capacity=cap, unit="L", scope="vehicle")
        ]
        vehicle = Vehicle(
            name=None,
            kind="truck",
            position=None,
            geo=None,
            attitude=None,
            velocity=Velocity(speed_mps=speed, vertical_mps=None, horizontal_mps=None),
            accel_g=None,
            controls=Controls(
                throttle=None,
                brake=None,
                steer=None,
                clutch=None,
                gear=int(data["gear"]) if data.get("gear") is not None else None,
                sas=None,
                rcs=None,
                parking_brake=None,
                cruise_control_mps=None,
                lights=None,
            ),
            engine=None,
            damage=Damage(overall=None, parts={}),
            situation=None,
            stage=None,
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
            t_game_s=(game_time_min or 0.0) * 60.0,
            paused=paused,
            scene=str(raw.get("scene", "driving")),
            domain=manifest.domain,
            vehicle=vehicle,
            resources=resources,
            environment=Environment(
                body=None,
                atmosphere_density=None,
                dynamic_pressure_pa=None,
                static_pressure_pa=None,
                speed_limit_mps=_float(data.get("speed_limit_mps")),
                weather=None,
                local_time=None,
            ),
            job=Job(
                active=job_active,
                cargo=None,
                mass_kg=None,
                source=None,
                destination=None,
                income=None,
                currency=self._currency,
                deadline_game_s=None,
                nav_distance_m=_float(data.get("nav_distance_m")),
                nav_time_s=None,
                trailer_attached=None,
                cargo_damage=_float(data.get("cargo_damage")),
            ),
            economy=None,
            game_specific=_scs_specific(data, raw),
        )

    def detect_events(
        self,
        prev: TelemetryFrame | None,
        cur: TelemetryFrame,
        raw: RawFrame,
    ) -> list[GameEvent]:
        del prev, cur
        return []

    def launch_stub(self, profile: GameProfile) -> dict[str, str | None]:
        manifest = self.load_manifest()
        return {
            "method": "steam_uri" if manifest.launch.steam_uri else "executable",
            "launch_uri": manifest.launch.steam_uri,
            "executable_path": profile.executable_path,
        }


def _float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _scs_specific(data: dict[str, Any], raw: RawFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if data.get("job_delivered") or raw.get("job_delivered"):
        out["job_delivered"] = True
    if data.get("player_fined") or raw.get("player_fined"):
        out["player_fined"] = True
    if "fine_amount" in raw:
        out["fine_amount"] = raw["fine_amount"]
    return out


def load_scs_manifest(manifest_root: Path) -> GameManifest:
    return GameManifest.from_yaml_path(manifest_root / "titan-game.yaml")
