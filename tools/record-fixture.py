#!/usr/bin/env python3
"""Append normalized raw telemetry frames to an NDJSON fixture (M5.T5)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Record or append telemetry fixture frames as NDJSON")
    parser.add_argument("fixture", type=Path, help="Output fixture path")
    parser.add_argument("--frame", type=Path, help="Single JSON object file to append")
    parser.add_argument("--json", help="Inline JSON object to append")
    args = parser.parse_args()
    if args.frame is None and args.json is None:
        parser.error("provide --frame or --json")
    if args.frame is not None:
        data = json.loads(args.frame.read_text(encoding="utf-8"))
    else:
        data = json.loads(args.json or "{}")
    if not isinstance(data, dict):
        print("frame must be a JSON object", file=sys.stderr)
        raise SystemExit(1)
    args.fixture.parent.mkdir(parents=True, exist_ok=True)
    with args.fixture.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(data, separators=(",", ":"), sort_keys=True) + "\n")
    print(f"appended 1 frame to {args.fixture}")


if __name__ == "__main__":
    main()
