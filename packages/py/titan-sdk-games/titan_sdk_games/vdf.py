"""Minimal Valve Data Format parser for Steam `libraryfolders.vdf` and `appmanifest_*.acf`."""

from __future__ import annotations

from typing import Any


def parse_vdf(text: str) -> dict[str, Any]:
    """Parse a VDF document into nested dicts (string keys and string leaf values)."""
    tokens = _tokenize(text)
    if not tokens:
        return {}
    if tokens[0] != "{":
        if len(tokens) >= 2 and tokens[1] == "{":
            value, _ = _parse_block(tokens, 1)
            return {tokens[0]: value}
        raise ValueError("VDF root must be a block")
    value, _ = _parse_block(tokens, 0)
    if not isinstance(value, dict):
        raise ValueError("VDF root must be a block")
    return value


def _tokenize(text: str) -> list[str]:
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in "{}":
            out.append(ch)
            i += 1
            continue
        if ch in " \t\r\n":
            i += 1
            continue
        if ch == '"':
            i += 1
            start = i
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                i += 1
            out.append(text[start:i])
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        start = i
        while i < n and text[i] not in '"{} \t\r\n':
            i += 1
        if start < i:
            out.append(text[start:i])
    return out


def _parse_block(tokens: list[str], index: int) -> tuple[Any, int]:
    if index >= len(tokens) or tokens[index] != "{":
        raise ValueError("expected '{'")
    index += 1
    block: dict[str, Any] = {}
    while index < len(tokens) and tokens[index] != "}":
        key = tokens[index]
        index += 1
        if index >= len(tokens):
            break
        tok = tokens[index]
        if tok == "{":
            val, index = _parse_block(tokens, index)
        else:
            val = tok
            index += 1
        if key in block:
            existing = block[key]
            if isinstance(existing, list):
                existing.append(val)
            else:
                block[key] = [existing, val]
        else:
            block[key] = val
    if index < len(tokens) and tokens[index] == "}":
        index += 1
    return block, index


def vdf_get_str(node: dict[str, Any], *path: str) -> str | None:
    cur: Any = node
    for part in path:
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return str(cur) if cur is not None else None
