"""Declarative event rule engine (Section 7.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml

from titan_core.clock import utc_now
from titan_core.protocol.events import EventMarker, GameEvent
from titan_core.protocol.telemetry import TelemetryFrame
from titan_telemetry.paths import read_path


@dataclass
class RuleSpec:
    id: str
    type: str
    when: dict[str, Any]
    severity: str
    salience: float
    payload: dict[str, Any] = field(default_factory=dict)
    for_s: float = 0.0
    cooldown_s: float = 0.0
    once_per_session: bool = False
    only_in_scene: list[str] | None = None
    marker: dict[str, Any] | None = None
    category: str = "game"


@dataclass
class _RuleState:
    for_since_s: float | None = None
    cooldown_until_s: float = 0.0
    fired_once: bool = False
    peak_windows: dict[str, list[tuple[float, float]]] = field(default_factory=dict)


class RuleEngine:
    def __init__(self, rules: list[RuleSpec], *, session_id: UUID, game: str) -> None:
        self.rules = rules
        self.session_id = session_id
        self.game = game
        self._prev: dict[str, Any] | None = None
        self._event_seq = 0
        self._state: dict[str, _RuleState] = {rule.id: _RuleState() for rule in rules}

    @classmethod
    def from_yaml(cls, path: Path, *, session_id: UUID, game: str) -> RuleEngine:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        specs: list[RuleSpec] = []
        if isinstance(raw, list):
            for row in raw:
                if isinstance(row, dict):
                    specs.append(
                        RuleSpec(
                            id=str(row["id"]),
                            type=str(row["type"]),
                            when=row.get("when") or {},
                            severity=str(row.get("severity", "info")),
                            salience=float(row.get("salience", 0.5)),
                            payload=row.get("payload") or {},
                            for_s=float(row.get("for_s", 0)),
                            cooldown_s=float(row.get("cooldown_s", 0)),
                            once_per_session=bool(row.get("once_per_session", False)),
                            only_in_scene=row.get("only_in_scene"),
                            marker=row.get("marker"),
                            category=str(row.get("category", "game")),
                        )
                    )
        return cls(specs, session_id=session_id, game=game)

    def evaluate(self, frame: TelemetryFrame, *, t_session_ms: int, paused: bool) -> list[GameEvent]:
        now_s = t_session_ms / 1000.0
        cur = frame.model_dump(mode="json", by_alias=True)
        out: list[GameEvent] = []
        for rule in self.rules:
            state = self._state[rule.id]
            if rule.once_per_session and state.fired_once:
                continue
            if rule.only_in_scene and frame.scene not in rule.only_in_scene:
                continue
            if paused and rule.type not in {"game.paused", "game.resumed"}:
                continue
            if now_s < state.cooldown_until_s:
                continue
            peak_ctx: dict[str, Any] = {}
            matched = self._eval_when(rule.when, cur, self._prev, now_s, state, peak_ctx)
            if rule.for_s > 0:
                if matched:
                    if state.for_since_s is None:
                        state.for_since_s = now_s
                    matched = (now_s - state.for_since_s) >= rule.for_s
                else:
                    state.for_since_s = None
            if not matched:
                continue
            self._event_seq += 1
            payload = self._build_payload(rule.payload, cur, peak_ctx)
            marker = None
            if rule.marker:
                marker = EventMarker(
                    kind=rule.marker["kind"], duration_ms=int(rule.marker.get("duration_ms", 0))
                )
            occurred = utc_now()
            out.append(
                GameEvent(
                    id=_stable_event_id(self.session_id, self._event_seq),
                    session_id=self.session_id,
                    seq=self._event_seq,
                    type=rule.type,
                    category=rule.category,  # type: ignore[arg-type]
                    severity=rule.severity,  # type: ignore[arg-type]
                    salience=rule.salience,
                    source=f"rule:{rule.id}",
                    t_mono_ns=frame.t_mono_ns,
                    t_session_ms=t_session_ms,
                    occurred_at=occurred,
                    frame_seq=frame.seq,
                    payload=payload,
                    marker=marker,
                )
            )
            state.fired_once = rule.once_per_session or state.fired_once
            if rule.cooldown_s > 0:
                state.cooldown_until_s = now_s + rule.cooldown_s
        self._prev = cur
        return out

    def _eval_when(
        self,
        when: dict[str, Any],
        cur: dict[str, Any],
        prev: dict[str, Any] | None,
        now_s: float,
        state: _RuleState,
        peak_ctx: dict[str, Any],
    ) -> bool:
        if "all" in when:
            items = when["all"]
            return isinstance(items, list) and all(
                self._eval_clause(item, cur, prev, now_s, state, peak_ctx)
                for item in items
                if isinstance(item, dict)
            )
        if "any" in when:
            items = when["any"]
            return isinstance(items, list) and any(
                self._eval_clause(item, cur, prev, now_s, state, peak_ctx)
                for item in items
                if isinstance(item, dict)
            )
        if "not" in when:
            inner = when["not"]
            return (
                not self._eval_when(inner, cur, prev, now_s, state, peak_ctx)
                if isinstance(inner, dict)
                else False
            )
        if "peak" in when:
            spec = when["peak"]
            return isinstance(spec, dict) and self._eval_peak(spec, cur, now_s, state, peak_ctx)
        if "path" in when and "op" in when:
            return self._eval_clause(when, cur, prev, now_s, state, peak_ctx)
        return False

    def _eval_clause(
        self,
        clause: dict[str, Any],
        cur: dict[str, Any],
        prev: dict[str, Any] | None,
        now_s: float,
        state: _RuleState,
        peak_ctx: dict[str, Any],
    ) -> bool:
        op = clause.get("op")
        path = clause.get("path")
        if not isinstance(op, str) or not isinstance(path, str):
            return False
        left = read_path(cur, path)
        if op == "is_null":
            return left is None
        right = clause.get("value")
        if op == "==":
            return bool(left == right)
        if op == "!=":
            return bool(left != right)
        if op in {"<", "<=", ">", ">="}:
            if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
                return False
            if op == "<":
                return left < right
            if op == "<=":
                return left <= right
            if op == ">":
                return left > right
            return left >= right
        if prev is None:
            return False
        prev_val = read_path(prev, path)
        if op == "changed":
            return bool(left != prev_val)
        if op == "changed_to":
            return bool(prev_val != right and left == right)
        if op == "changed_from":
            return bool(prev_val == right and left != right)
        if op == "crossed_above" and isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return isinstance(prev_val, (int, float)) and prev_val <= right < left
        if op == "crossed_below" and isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return isinstance(prev_val, (int, float)) and prev_val >= right > left
        return False

    def _eval_peak(
        self,
        spec: dict[str, Any],
        cur: dict[str, Any],
        now_s: float,
        state: _RuleState,
        peak_ctx: dict[str, Any],
    ) -> bool:
        path = spec.get("path")
        window_s = float(spec.get("window_s", 1))
        min_value = float(spec.get("min_value", 0))
        if not isinstance(path, str):
            return False
        value = read_path(cur, path)
        if not isinstance(value, (int, float)):
            return False
        bucket = state.peak_windows.setdefault(path, [])
        bucket.append((now_s, float(value)))
        cutoff = now_s - window_s
        state.peak_windows[path] = [(t, v) for t, v in bucket if t >= cutoff]
        window = state.peak_windows[path]
        if len(window) < 2:
            return False
        peak = max(v for _, v in window)
        if peak < min_value:
            return False
        _, last = window[-1]
        prev_val = window[-2][1]
        if last < peak and prev_val >= peak:
            peak_ctx["$peak"] = peak
            peak_ctx[path] = peak
            return True
        return False

    def _build_payload(
        self, template: dict[str, Any], cur: dict[str, Any], peak_ctx: dict[str, Any]
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in template.items():
            if isinstance(value, str):
                if value.startswith("$"):
                    out[key] = peak_ctx.get(value, value)
                else:
                    out[key] = read_path(cur, value)
            elif isinstance(value, dict) and "path" in value:
                raw = read_path(cur, str(value["path"]))
                scale = value.get("scale")
                if isinstance(raw, (int, float)) and isinstance(scale, (int, float)):
                    out[key] = raw * scale
                else:
                    out[key] = raw
            else:
                out[key] = value
        return out


def _stable_event_id(session_id: UUID, seq: int) -> UUID:
    from uuid import NAMESPACE_URL, uuid5

    return uuid5(NAMESPACE_URL, f"titan-event:{session_id}:{seq}")
