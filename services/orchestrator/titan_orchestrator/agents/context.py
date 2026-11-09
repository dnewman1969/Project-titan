"""Prompt context builder with token budget (M6.T3)."""

from __future__ import annotations

from typing import Any

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def build_context(
    *,
    system_prompt: str,
    tasks: list[dict[str, Any]],
    blackboard: list[dict[str, Any]],
    world_state: dict[str, Any] | None,
    chat_lines: list[str],
    memories: list[str],
    budget_tokens: int = 3000,
) -> str:
    sections: list[tuple[int, str]] = []
    sections.append((9, f"System:\n{system_prompt}"))
    if tasks:
        task_text = "\n".join(f"- {item.get('title', item)}" for item in tasks[:5])
        sections.append((8, f"Open tasks:\n{task_text}"))
    if world_state:
        sections.append((7, f"World state:\n{world_state}"))
    if blackboard:
        bb_text = "\n".join(f"{row['section']}/{row['key']}: {row.get('value')}" for row in blackboard[:30])
        sections.append((6, f"Blackboard:\n{bb_text}"))
    if memories:
        sections.append((5, "Memories:\n" + "\n".join(memories[:5])))
    if chat_lines:
        sections.append((4, "Recent chat:\n" + "\n".join(chat_lines[-12:])))
    sections.sort(key=lambda item: item[0], reverse=True)
    parts: list[str] = []
    used = 0
    for _priority, block in sections:
        need = estimate_tokens(block)
        if used + need > budget_tokens:
            remaining = max(budget_tokens - used, 0) * CHARS_PER_TOKEN
            if remaining > 0:
                parts.append(block[:remaining])
            break
        parts.append(block)
        used += need
    return "\n\n".join(parts)
