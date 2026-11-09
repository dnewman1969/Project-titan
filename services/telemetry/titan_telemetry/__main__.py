"""CLI entry: `titan-telemetry --session-id ...`."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

from titan_core.config import load_config
from titan_core.logging import configure_logging, get_logger
from titan_sdk_games.adapter import AdapterConfig, GameAdapter, RawFrame
from titan_sdk_games.profiles import GameProfile
from titan_telemetry.host import TelemetryHost
from titan_telemetry.loader import adapter_for, rules_path
from titan_telemetry.pipeline import canonical_events_ndjson, iter_fixture, run_fixture

log = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(prog="titan-telemetry")
    parser.add_argument("--session-id", type=UUID, required=False)
    parser.add_argument("--game", required=True, help="Game slug, e.g. ksp")
    parser.add_argument("--replay", type=Path, help="Fixture NDJSON path")
    parser.add_argument("--golden", action="store_true", help="Print canonical events JSON for golden files")
    parser.add_argument("--speed", type=int, default=1, choices=[1, 2, 10])
    parser.add_argument("--install-path", default=".")
    args = parser.parse_args()
    configure_logging("titan-telemetry")
    adapter_cls = adapter_for(args.game)
    adapter = adapter_cls()
    profile = GameProfile(
        id=None,
        game_id=None,
        store="standalone",
        install_path=args.install_path,
        executable_path="game.exe",
    )

    if args.replay is not None:
        session_id = args.session_id or UUID(int=0)
        if args.golden:
            result = run_fixture(
                adapter,
                rules_path(adapter_cls),
                args.replay,
                session_id=session_id,
                game=args.game,
                adapter_version=adapter_cls.load_manifest().adapter_version,
            )
            print(canonical_events_ndjson(result.events), end="")
            return
        asyncio.run(_run_replay(adapter, profile, args, session_id))
        return

    if args.session_id is None:
        parser.error("--session-id is required without --replay")
    asyncio.run(_run_live(adapter, profile, args.session_id, args.game))


async def _run_live(adapter: GameAdapter, profile: GameProfile, session_id: UUID, game: str) -> None:
    await adapter.connect(profile, AdapterConfig())
    host = TelemetryHost.from_config(
        load_config(),
        session_id=session_id,
        adapter=adapter,
        game=game,
        profile=profile,
    )
    try:
        await host.run_live()
    finally:
        host.close()
        await adapter.disconnect()


async def _run_replay(
    adapter: GameAdapter,
    profile: GameProfile,
    args: argparse.Namespace,
    session_id: UUID,
) -> None:
    await adapter.connect(profile, AdapterConfig(replay_path=str(args.replay)))
    host = TelemetryHost.from_config(
        load_config(),
        session_id=session_id,
        adapter=adapter,
        game=args.game,
        profile=profile,
    )

    async def _aiter() -> AsyncIterator[RawFrame]:
        for raw in iter_fixture(args.replay):
            yield raw

    try:
        await host.run_replay(_aiter(), speed=args.speed)
    finally:
        host.close()
        await adapter.disconnect()


if __name__ == "__main__":
    main()
