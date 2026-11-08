"""`titan-db` command: apply or roll back migrations using the layered Titan config."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from titan_core.config import load_config
from titan_db import migrate


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="titan-db", description="Titan database migrations")
    sub = parser.add_subparsers(dest="command", required=True)
    up = sub.add_parser("upgrade", help="apply migrations (default: head)")
    up.add_argument("revision", nargs="?", default="head")
    down = sub.add_parser("downgrade", help="roll back migrations (default: base)")
    down.add_argument("revision", nargs="?", default="base")
    args = parser.parse_args(argv)

    url = migrate.database_url(load_config().postgres)
    if args.command == "upgrade":
        migrate.upgrade(url, args.revision)
    else:
        migrate.downgrade(url, args.revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
