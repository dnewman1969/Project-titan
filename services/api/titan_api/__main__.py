"""`titan-api` entry point: `uv run titan-api` or `python -m titan_api`."""

from __future__ import annotations

import uvicorn

from titan_api.main import create_app
from titan_core.config import expand_path, load_config
from titan_core.logging import configure_logging


def main() -> None:
    cfg = load_config()
    configure_logging("titan-api", level=cfg.logging.level, log_dir=expand_path("%LOCALAPPDATA%/Titan/logs"))
    # One worker, loopback only (Section 2.3 and 9.6).
    uvicorn.run(create_app(cfg), host=cfg.api.host, port=cfg.api.port, workers=1, log_config=None)


if __name__ == "__main__":
    main()
