"""Protocol models: the single source of truth for wire formats (decision D14).

JSON Schemas in `schemas/` and the TypeScript types and zod validators in
`packages/ts/protocol` are generated from these models by `tools/codegen.py`. Never edit the
generated files by hand; CI fails if they drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from titan_core.protocol import envelope, events, payloads, system, telemetry, ws
from titan_core.protocol.envelope import ENVELOPE_SCHEMA, Address, Envelope, make_envelope
from titan_core.protocol.events import GameEvent
from titan_core.protocol.payloads import MESSAGE_TYPES, parse_payload
from titan_core.protocol.telemetry import TELEMETRY_SCHEMA, TelemetryFrame, TelemetryFrameUI


@dataclass(frozen=True)
class SchemaFile:
    """One generated file `schemas/<name>.json`."""

    name: str
    title: str
    models: tuple[type[BaseModel], ...]
    root: type[BaseModel] | None = None
    """Inlined at the top level of the file; the other models go in `$defs`."""
    type_maps: dict[str, dict[str, type[BaseModel]]] = field(default_factory=dict)
    """Extra `x-titan-*` keywords mapping a message `type` to a `$defs` entry."""


_WS_MODELS: tuple[type[BaseModel], ...] = (
    ws.ClientFrame,
    ws.ServerFrame,
    ws.AuthFrame,
    ws.SubscribeFrame,
    ws.UnsubscribeFrame,
    ws.PingFrame,
    ws.AckFrame,
    ws.MsgFrame,
    ws.PongFrame,
    ws.GapFrame,
    *ws.WS_MESSAGE_TYPES.values(),
)

SCHEMA_FILES: tuple[SchemaFile, ...] = (
    SchemaFile("envelope", "Envelope", (Envelope,), root=Envelope),
    SchemaFile(
        "payloads",
        "Envelope payloads",
        tuple(dict.fromkeys(MESSAGE_TYPES.values())),
        type_maps={"x-titan-message-types": dict(MESSAGE_TYPES)},
    ),
    SchemaFile("telemetry", "TelemetryFrame", (TelemetryFrame, TelemetryFrameUI), root=TelemetryFrame),
    SchemaFile("events", "GameEvent", (GameEvent,), root=GameEvent),
    SchemaFile(
        "ws",
        "WebSocket protocol",
        tuple(dict.fromkeys(_WS_MODELS)),
        type_maps={"x-titan-ws-message-types": dict(ws.WS_MESSAGE_TYPES)},
    ),
    SchemaFile(
        "system",
        "System status and safety",
        (
            system.SystemStatus,
            system.SupervisorStatus,
            system.GameTarget,
            system.SafetyKillRequest,
            system.SafetyResumeRequest,
            system.SafetyArmRequest,
        ),
    ),
)

__all__ = [
    "ENVELOPE_SCHEMA",
    "MESSAGE_TYPES",
    "SCHEMA_FILES",
    "TELEMETRY_SCHEMA",
    "Address",
    "Envelope",
    "GameEvent",
    "SchemaFile",
    "TelemetryFrame",
    "TelemetryFrameUI",
    "envelope",
    "events",
    "make_envelope",
    "parse_payload",
    "payloads",
    "system",
    "telemetry",
    "ws",
]
