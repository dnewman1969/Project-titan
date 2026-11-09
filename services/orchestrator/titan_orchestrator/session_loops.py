"""Live session background loops: telemetry → blackboard, events → crew learnings."""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from titan_core.ids import uuid7
from titan_core.protocol.envelope import Address, make_envelope
from titan_core.protocol.events import GameEvent
from titan_core.protocol.payloads import ActionPropose
from titan_core.protocol.telemetry import TelemetryFrameUI
from titan_core.streams import entry_data, session_events_stream, session_telemetry_stream
from titan_orchestrator.play_policy import play_proposal_for_event
from titan_orchestrator.runtime import SessionRuntime
from titan_orchestrator.world_state import WorldStateUpdater


async def run_session_loops(runtime: SessionRuntime, *, play_enabled: bool = False) -> None:
    """Run until runtime.stop() is called."""
    telemetry_task = asyncio.create_task(_telemetry_loop(runtime), name="telemetry-loop")
    events_task = asyncio.create_task(_events_loop(runtime, play_enabled=play_enabled), name="events-loop")
    try:
        await asyncio.gather(telemetry_task, events_task)
    finally:
        for task in (telemetry_task, events_task):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def _telemetry_loop(runtime: SessionRuntime) -> None:
    stream = session_telemetry_stream(str(runtime.session_id))
    last_id = "$"
    while not runtime._stopped.is_set():
        rows: Any = await runtime.redis.xread({stream: last_id}, count=8, block=2000)
        if not rows:
            continue
        async with runtime.sessions() as db:
            bb = runtime.blackboard_service(db)
            updater = WorldStateUpdater(
                runtime.session_id,
                runtime.redis,
                bb,
                emit=runtime.bus.publish,
            )
            for _stream_name, entries in rows:
                for entry_id, fields in entries:
                    last_id = entry_id
                    if not fields:
                        continue
                    try:
                        payload = TelemetryFrameUI.model_validate_json(entry_data(fields))
                    except (ValueError, json.JSONDecodeError):
                        continue
                    frame = payload.model_dump(by_alias=True)
                    await updater.ingest_telemetry(
                        {"summary": frame},
                        scene=str(frame.get("scene", "live")),
                    )
            await db.commit()


async def _events_loop(runtime: SessionRuntime, *, play_enabled: bool) -> None:
    stream = session_events_stream(str(runtime.session_id))
    last_id = "$"
    seq = 0
    while not runtime._stopped.is_set():
        rows: Any = await runtime.redis.xread({stream: last_id}, count=16, block=2000)
        if not rows:
            continue
        async with runtime.sessions() as db:
            bb = runtime.blackboard_service(db)
            for _stream_name, entries in rows:
                for entry_id, fields in entries:
                    last_id = entry_id
                    if not fields:
                        continue
                    try:
                        event = GameEvent.model_validate_json(entry_data(fields))
                    except (ValueError, json.JSONDecodeError):
                        continue
                    runtime.event_router.route(event, runtime.session_id)
                    seq += 1
                    lesson_key = f"event.{seq:05d}"
                    await bb.put(
                        section="discoveries",
                        key=lesson_key,
                        value={
                            "text": _event_line(event),
                            "event_type": event.type,
                        },
                        author=Address(kind="agent", id="flight_engineer"),
                        expected_version=-1,
                        confidence=0.85,
                    )
                    if play_enabled:
                        proposal = play_proposal_for_event(event)
                        if proposal is not None:
                            await runtime.bus.publish(
                                make_envelope(
                                    type="action.propose",
                                    session_id=runtime.session_id,
                                    sender=Address(kind="agent", id="director"),
                                    recipients=["role:actions"],
                                    visibility="internal",
                                    priority=6,
                                    payload=ActionPropose.model_validate(proposal),
                                    correlation_id=uuid7(),
                                )
                            )
                            await bb.put(
                                section="lessons",
                                key=f"play.{lesson_key}",
                                value={"text": proposal["rationale"], "action_id": proposal["action_id"]},
                                author=Address(kind="agent", id="director"),
                                expected_version=-1,
                                confidence=0.9,
                            )
            await db.commit()


def _event_line(event: GameEvent) -> str:
    label = event.type.replace(".", " ").replace("_", " ")
    if event.salience >= 0.8:
        return f"Critical: {label} — note it for the playbook."
    if event.salience >= 0.5:
        return f"Noted {label}; updating mental model."
    return f"Saw {label}."
