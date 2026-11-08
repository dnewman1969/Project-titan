"""Helpers for running plain SQL scripts through drivers that execute one statement at a time."""

from __future__ import annotations

import re

_LINE_COMMENT = re.compile(r"--[^\n]*")
_TABLE = re.compile(r"^CREATE TABLE (\w+)", re.MULTILINE)


def strip_comments(script: str) -> str:
    """Remove `--` line comments. The Titan DDL has no `--` inside string literals."""
    return _LINE_COMMENT.sub("", script)


def split_statements(script: str) -> list[str]:
    """Split a script into statements on semicolons that end a line.

    This keeps `$$ ... $$` function bodies intact as long as their inner semicolons are not
    at the end of a line, which holds for the Titan DDL (Section 4.2).
    """
    statements: list[str] = []
    current: list[str] = []
    for line in strip_comments(script).splitlines():
        current.append(line)
        if line.rstrip().endswith(";"):
            statement = "\n".join(current).strip()
            if statement != ";":
                statements.append(statement.removesuffix(";").strip())
            current = []
    rest = "\n".join(current).strip()
    if rest:
        statements.append(rest)
    return [s for s in statements if s]


def created_tables(script: str) -> list[str]:
    """Names of tables created by `script`, in creation order."""
    return _TABLE.findall(strip_comments(script))
