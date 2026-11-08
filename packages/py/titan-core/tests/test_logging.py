from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from titan_core import logging as tlog


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    yield
    tlog.clear_context()
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()


def lines(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def test_json_lines_with_standard_fields_and_context() -> None:
    stream = io.StringIO()
    tlog.configure_logging("titan-test", stream=stream)
    tlog.bind_context(session_id="0193f19c-0000-7000-8000-00000000aaaa", task_id="t1")
    tlog.get_logger("unit").info("session_started", game="ksp")
    (record,) = lines(stream)
    assert record["event"] == "session_started"
    assert record["level"] == "info"
    assert record["process"] == "titan-test"
    assert isinstance(record["pid"], int)
    assert record["logger"] == "unit"
    assert record["session_id"] == "0193f19c-0000-7000-8000-00000000aaaa"
    assert record["game"] == "ksp"
    assert str(record["ts"]).endswith("Z")


def test_secrets_are_redacted_recursively() -> None:
    stream = io.StringIO()
    tlog.configure_logging("titan-test", stream=stream)
    tlog.get_logger().info(
        "connect", launch_token="abc", headers={"Authorization": "Bearer abc", "accept": "json"}, user="me"
    )
    (record,) = lines(stream)
    assert record["launch_token"] == tlog.REDACTED
    assert record["headers"] == {"Authorization": tlog.REDACTED, "accept": "json"}
    assert record["user"] == "me"
    assert "abc" not in stream.getvalue()


def test_level_filtering_and_stdlib_bridge() -> None:
    stream = io.StringIO()
    tlog.configure_logging("titan-test", level="WARNING", stream=stream)
    tlog.get_logger().info("hidden")
    logging.getLogger("thirdparty").warning("from stdlib api_key=%s", "x")
    (record,) = lines(stream)
    assert record["event"] == "from stdlib api_key=x"
    assert record["logger"] == "thirdparty"


def test_rotating_file_handler(tmp_path: Path) -> None:
    tlog.configure_logging("titan-api", log_dir=tmp_path, stream=io.StringIO())
    tlog.get_logger().info("to_file")
    for handler in logging.getLogger().handlers:
        handler.flush()
    log_file = tmp_path / "titan-api" / "titan-api.log"
    assert json.loads(log_file.read_text(encoding="utf-8").splitlines()[0])["event"] == "to_file"
    rotating = [
        h for h in logging.getLogger().handlers if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    assert rotating[0].maxBytes == 50 * 1024 * 1024
    assert rotating[0].backupCount == 10


def test_bind_context_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="unknown context fields"):
        tlog.bind_context(user_id="x")


def test_redact_mapping() -> None:
    assert tlog.redact_mapping({"db_password": "x", "port": 1}) == {"db_password": tlog.REDACTED, "port": 1}
