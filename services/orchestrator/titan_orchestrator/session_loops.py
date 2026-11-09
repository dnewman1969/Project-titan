"""Live session background loops: telemetry -> blackboard, events -> crew learnings."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from titan_core.bus import ORCH_CONSUMER, ORCH_GROUP
from titan_core.ids import uuid7
from titan_core.logging import get_logger
from titan_core.protocol.envelope import Address, make_envelope
from titan_core.protocol.events import GameEvent
from titan_core.protocol.payloads import ActionExecuted, ActionPropose
from titan_core.protocol.telemetry import TelemetryFrameUI
from titan_core.streams import (
    BUS_BLOCK_MS,
    IDLE_READ_ERRORS,
    entry_data,
    latest_entry,
    session_events_stream,
    session_telemetry_stream,
)
from titan_orchestrator.errors import PermissionDenied, RateLimited
from titan_orchestrator.flight_policy import command_signature, decide_flight
from titan_orchestrator.play_commentary import pick_play_commentary
from titan_orchestrator.play_policy import PlayMemory, play_memory_for, play_proposal_for_event
from titan_orchestrator.rec_timeline import append_rec_timeline
from titan_orchestrator.runtime import SessionRuntime
from titan_orchestrator.world_state import WorldStateUpdater

log = get_logger(__name__)
_FLY_FEEDBACK_MIN_S = 4.0


async def run_session_loops(
    runtime: SessionRuntime,
    *,
    play_enabled: bool = False,
    game_slug: str | None = None,
    flight_period_s: float = 1.0,
) -> None:
    """Run until runtime.stop() is called."""
    await runtime.bus.ensure_group(ORCH_GROUP)
    telemetry_task = asyncio.create_task(_telemetry_loop(runtime), name="telemetry-loop")
    events_task = asyncio.create_task(_events_loop(runtime, play_enabled=play_enabled), name="events-loop")
    tasks = [telemetry_task, events_task]
    if play_enabled:
        tasks.append(asyncio.create_task(_play_feedback_loop(runtime), name="play-feedback-loop"))
        if (game_slug or "").strip().lower() == "ksp":
            tasks.append(
                asyncio.create_task(
                    _flight_loop(runtime, period_s=flight_period_s),
                    name="flight-loop",
                )
            )
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def _telemetry_loop(runtime: SessionRuntime) -> None:
    stream = session_telemetry_stream(str(runtime.session_id))
    last_id = "$"
    while not runtime._stopped.is_set():
        rows: Any = await _block_xread(runtime.redis, {stream: last_id}, count=8, block_ms=BUS_BLOCK_MS)
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
    session_key = str(runtime.session_id)
    memory = play_memory_for(session_key)
    while not runtime._stopped.is_set():
        rows: Any = await _block_xread(runtime.redis, {stream: last_id}, count=16, block_ms=BUS_BLOCK_MS)
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
                    await _safe_bb_put(
                        bb,
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
                        proposal = play_proposal_for_event(event, memory=memory)
                        if proposal is not None:
                            envelope = make_envelope(
                                type="action.propose",
                                session_id=runtime.session_id,
                                sender=Address(kind="agent", id="director"),
                                recipients=["role:actions"],
                                visibility="internal",
                                priority=6,
                                payload=ActionPropose.model_validate(proposal),
                                correlation_id=uuid7(),
                            )
                            memory.remember_proposal(str(envelope.id), str(proposal["action_id"]))
                            await runtime.bus.publish(envelope)
                            await _safe_bb_put(
                                bb,
                                section="lessons",
                                key=f"play.{lesson_key}",
                                value={
                                    "text": proposal["rationale"],
                                    "action_id": proposal["action_id"],
                                    "params": proposal.get("params", {}),
                                },
                                author=Address(kind="agent", id="director"),
                                expected_version=-1,
                                confidence=0.9,
                            )
                            append_rec_timeline(
                                kind="lesson.proposed",
                                payload={
                                    "action_id": proposal["action_id"],
                                    "text": proposal["rationale"],
                                    "event_type": event.type,
                                },
                            )
            await db.commit()


async def _play_feedback_loop(runtime: SessionRuntime) -> None:
    session_key = str(runtime.session_id)
    memory = play_memory_for(session_key)
    last_fly_feedback = 0.0
    while not runtime._stopped.is_set():
        try:
            batch = await runtime.bus.read_group(ORCH_GROUP, ORCH_CONSUMER, block_ms=BUS_BLOCK_MS)
        except IDLE_READ_ERRORS:
            continue
        if not batch:
            await asyncio.sleep(0)
            continue
        async with runtime.sessions() as db:
            bb = runtime.blackboard_service(db)
            for entry_id, envelope in batch:
                try:
                    if envelope.type != "action.executed":
                        continue
                    payload = ActionExecuted.model_validate(envelope.payload)
                    action_id = memory.record_outcome(
                        proposal_id=str(payload.proposal_id),
                        ok=payload.ok,
                    )
                    now = time.monotonic()
                    # The flight loop refreshes ksp.fly every second. Keep the learn
                    # strip moving without hitting the per-author blackboard rate cap.
                    if (
                        action_id == "ksp.fly"
                        and payload.ok
                        and (now - last_fly_feedback) < _FLY_FEEDBACK_MIN_S
                    ):
                        continue
                    if action_id == "ksp.fly" and payload.ok:
                        last_fly_feedback = now
                    if payload.ok:
                        action_bit = f" ({action_id})" if action_id else ""
                        text = f"Play worked{action_bit} - crew should repeat this control pattern."
                    else:
                        detail = payload.error or "unknown error"
                        action_bit = f" for {action_id}" if action_id else ""
                        text = f"Play attempt failed{action_bit}: {detail}"
                    await _safe_bb_put(
                        bb,
                        section="lessons",
                        key=f"feedback.{envelope.id}",
                        value={
                            "text": text,
                            "proposal_id": str(payload.proposal_id),
                            "action_id": action_id,
                            "ok": payload.ok,
                            "latency_ms": payload.latency_ms,
                        },
                        author=Address(kind="agent", id="flight_engineer"),
                        expected_version=-1,
                        confidence=0.92 if payload.ok else 0.4,
                    )
                    append_rec_timeline(
                        kind="lesson.feedback",
                        payload={
                            "text": text,
                            "proposal_id": str(payload.proposal_id),
                            "action_id": action_id,
                            "ok": payload.ok,
                        },
                    )
                    banter = pick_play_commentary(ok=payload.ok, impressive=payload.ok)
                    await _safe_bb_put(
                        bb,
                        section="notes",
                        key=f"commentary.{envelope.id}",
                        value={
                            "text": banter["text"],
                            "kind": banter["kind"],
                            "ok": payload.ok,
                            "action_id": action_id,
                            "commentary": True,
                        },
                        author=Address(kind="agent", id=banter["persona_slug"]),
                        expected_version=-1,
                        confidence=0.7,
                    )
                    append_rec_timeline(
                        kind="agent.commentary",
                        payload={
                            "persona_slug": banter["persona_slug"],
                            "display_name": banter["display_name"],
                            "role": banter["role"],
                            "text": banter["text"],
                            "ok": payload.ok,
                            "action_id": action_id,
                        },
                    )
                except Exception:
                    log.exception("play_feedback_item_failed", entry_id=entry_id)
                finally:
                    await runtime.bus.ack(ORCH_GROUP, entry_id)
            await db.commit()


@dataclass
class _FlightState:
    launch_staged: bool = False
    last_sig: tuple[object, ...] | None = None
    lesson_n: int = 0
    statuses: set[str] = field(default_factory=set)


async def _flight_loop(runtime: SessionRuntime, *, period_s: float) -> None:
    """Publish ksp.fly from the latest telemetry, or say when there is nothing to fly."""
    state = _FlightState()
    memory = play_memory_for(str(runtime.session_id))
    while not runtime._stopped.is_set():
        try:
            await _flight_tick(runtime, state, memory)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("flight_tick_failed", session_id=str(runtime.session_id))
        if runtime._stopped.is_set():
            return
        try:
            await asyncio.wait_for(runtime._stopped.wait(), timeout=max(0.05, period_s))
        except TimeoutError:
            continue
        return


async def _flight_tick(runtime: SessionRuntime, state: _FlightState, memory: PlayMemory) -> None:
    stream = session_telemetry_stream(str(runtime.session_id))
    try:
        latest = await latest_entry(runtime.redis, stream)
    except IDLE_READ_ERRORS:
        latest = None
    if latest is None:
        await _flight_status(
            runtime,
            state,
            status="waiting",
            message="No vessel telemetry yet — not steering. Waiting for a flight frame from kRPC.",
        )
        return
    _entry_id, data = latest
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return
    if not isinstance(payload, dict):
        return
    decision = decide_flight(payload)
    if decision.situation == "landed":
        state.launch_staged = False
    staging = bool(decision.stage_once and not state.launch_staged)
    if staging:
        state.launch_staged = True
    await _flight_status(runtime, state, status=decision.status, message=decision.message)
    if decision.proposal is None:
        return
    params = dict(decision.proposal.get("params") or {})
    if staging:
        params["stage"] = True
    proposal = {**decision.proposal, "params": params}
    envelope = make_envelope(
        type="action.propose",
        session_id=runtime.session_id,
        sender=Address(kind="agent", id="director"),
        recipients=["role:actions"],
        visibility="internal",
        priority=6,
        payload=ActionPropose.model_validate(proposal),
        correlation_id=uuid7(),
    )
    memory.remember_proposal(str(envelope.id), "ksp.fly")
    await runtime.bus.publish(envelope)
    sig = command_signature(decision, staging=staging)
    if sig == state.last_sig:
        return
    state.last_sig = sig
    state.lesson_n += 1
    async with runtime.sessions() as db:
        bb = runtime.blackboard_service(db)
        await _safe_bb_put(
            bb,
            section="lessons",
            key=f"play.flight.{state.lesson_n}",
            value={
                "text": str(proposal.get("rationale") or decision.message),
                "action_id": "ksp.fly",
                "params": params,
            },
            author=Address(kind="agent", id="director"),
            expected_version=-1,
            confidence=0.9,
        )
        await db.commit()
    append_rec_timeline(
        kind="lesson.proposed",
        payload={
            "action_id": "ksp.fly",
            "text": str(proposal.get("rationale") or decision.message),
            "event_type": "ksp.fly",
        },
    )


async def _flight_status(runtime: SessionRuntime, state: _FlightState, *, status: str, message: str) -> None:
    if status in state.statuses:
        return
    async with runtime.sessions() as db:
        bb = runtime.blackboard_service(db)
        await _safe_bb_put(
            bb,
            section="discoveries",
            key=f"flight.{status}",
            value={
                "text": message,
                "action_id": None if status in {"no_vessel", "waiting", "paused"} else "ksp.fly",
            },
            author=Address(kind="agent", id="flight_engineer"),
            expected_version=-1,
            confidence=0.86,
        )
        await db.commit()
    state.statuses.add(status)


async def _block_xread(redis: Any, streams: dict[str, str], *, count: int, block_ms: int) -> Any:
    try:
        return await redis.xread(streams, count=count, block=block_ms)
    except IDLE_READ_ERRORS:
        return None


async def _safe_bb_put(bb: Any, **kwargs: Any) -> None:
    try:
        await bb.put(**kwargs)
    except (PermissionDenied, RateLimited):
        log.info(
            "blackboard_write_skipped",
            section=kwargs.get("section"),
            key=kwargs.get("key"),
        )


def _event_line(event: GameEvent) -> str:
    label = event.type.replace(".", " ").replace("_", " ")
    if event.salience >= 0.8:
        return f"Critical: {label} - note it for the playbook."
    if event.salience >= 0.5:
        return f"Noted {label}; updating mental model."
    return f"Saw {label}."
