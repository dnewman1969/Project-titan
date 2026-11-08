"""structlog JSON logging with context variables and secret redaction (Section 9.4).

Each process calls `configure_logging(process=...)` once. Log lines are JSON objects with the
standard fields `ts, level, process, pid, logger, event` plus any bound context variables
(`session_id`, `correlation_id`, `agent_instance_id`, `task_id`, `trace_id`). Values whose key
looks like a secret are replaced with `[REDACTED]`.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import re
import sys
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

SECRET_KEY = re.compile(r"(?i)(token|secret|password|authorization|api_key)")
REDACTED = "[REDACTED]"
CONTEXT_FIELDS = ("session_id", "correlation_id", "agent_instance_id", "task_id", "trace_id")
MAX_BYTES = 50 * 1024 * 1024
BACKUP_COUNT = 10


def _redact_value(key: str, value: Any) -> Any:
    if SECRET_KEY.search(key):
        return REDACTED
    if isinstance(value, Mapping):
        return {k: _redact_value(str(k), v) for k, v in value.items()}
    return value


def redact_secrets(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """structlog processor: redact values whose key matches `SECRET_KEY`, recursively."""
    for key in list(event_dict):
        if key == "event":
            continue
        event_dict[key] = _redact_value(key, event_dict[key])
    return event_dict


def _add_process(process: str) -> Processor:
    pid = os.getpid()

    def processor(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
        event_dict.setdefault("process", process)
        event_dict.setdefault("pid", pid)
        return event_dict

    return processor


def shared_processors(process: str) -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
        _add_process(process),
        redact_secrets,
        structlog.processors.format_exc_info,
    ]


def configure_logging(
    process: str,
    *,
    level: str = "INFO",
    log_dir: Path | None = None,
    stream: Any = None,
) -> None:
    """Configure structlog and the stdlib root logger to emit JSON lines.

    When `log_dir` is given, logs also go to `<log_dir>/<process>/<process>.log`, rotating
    at 50 MB with 10 backups.
    """
    processors = shared_processors(process)
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )
    handlers: list[logging.Handler] = [logging.StreamHandler(stream or sys.stderr)]
    if log_dir is not None:
        target = log_dir / process
        target.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.handlers.RotatingFileHandler(
                target / f"{process}.log", maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
            )
        )
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(level)

    structlog.configure(
        processors=[*processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.stdlib.get_logger(name)
    return logger


def bind_context(**values: Any) -> None:
    """Bind standard context fields for the current task or thread."""
    unknown = set(values) - set(CONTEXT_FIELDS)
    if unknown:
        raise ValueError(f"unknown context fields: {sorted(unknown)}")
    structlog.contextvars.bind_contextvars(**values)


def clear_context() -> None:
    structlog.contextvars.clear_contextvars()


def redact_mapping(data: MutableMapping[str, Any]) -> dict[str, Any]:
    """Return a copy of `data` with secret-looking keys redacted (diagnostics bundle helper)."""
    return {k: _redact_value(k, v) for k, v in data.items()}
