"""`python -m titan_actions --session-id ...` — closed-loop play (beta)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import UUID

from titan_actions.executor import PlayExecutor
from titan_core.bus import SessionBus
from titan_core.config import load_config
from titan_core.logging import configure_logging, get_logger
from titan_core.protocol.envelope import Address, make_envelope
from titan_core.protocol.payloads import ActionExecuted, ActionPropose
from titan_core.streams import redis_client

log = get_logger(__name__)
ACTIONS_GROUP = "actions"
ACTIONS_CONSUMER = "actions-1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="titan-actions")
    parser.add_argument("--session-id", type=UUID, required=True)
    return parser.parse_args(argv)


async def _run(session_id: UUID) -> int:
    cfg = load_config()
    redis = redis_client(cfg.redis)
    bus = SessionBus(redis, session_id)
    await bus.ensure_group(ACTIONS_GROUP)
    executor = PlayExecutor(session_id=session_id)
    try:
        while True:
            batch = await bus.read_group(ACTIONS_GROUP, ACTIONS_CONSUMER, block_ms=2000)
            for entry_id, envelope in batch:
                if envelope.type != "action.propose":
                    await bus.ack(ACTIONS_GROUP, entry_id)
                    continue
                payload = ActionPropose.model_validate(envelope.payload)
                if payload.risk not in ("low", "medium"):
                    await bus.ack(ACTIONS_GROUP, entry_id)
                    continue
                ok, err = executor.execute(payload.action_id, dict(payload.params))
                log.info(
                    "action_executed",
                    action_id=payload.action_id,
                    ok=ok,
                    err=err,
                    session_id=str(session_id),
                )
                executed = ActionExecuted(
                    proposal_id=envelope.id,
                    ok=ok,
                    latency_ms=1,
                    error=err,
                )
                await bus.publish(
                    make_envelope(
                        type="action.executed",
                        session_id=session_id,
                        sender=Address(kind="agent", id="actions"),
                        recipients=["broadcast"],
                        visibility="internal",
                        priority=5,
                        payload=executed,
                        correlation_id=envelope.id,
                        causation_id=envelope.id,
                    )
                )
                await bus.ack(ACTIONS_GROUP, entry_id)
    except asyncio.CancelledError:
        pass
    finally:
        await redis.aclose()
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging("titan-actions")
    args = parse_args(argv)
    try:
        return asyncio.run(_run(args.session_id))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
