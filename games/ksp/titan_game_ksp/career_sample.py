"""Read KSP career state from a kRPC-shaped connection.

Duck-typed like ``vessel_sample``: unit tests pass a fake contract manager.
Stock kRPC exposes ``SpaceCenter.game_mode``, funds, science, reputation, and
``ContractManager`` (offered, active, failed, parameters, rewards). No other
mod is required. Sandbox saves have no contract manager that we will pretend
is a career.
"""

from __future__ import annotations

from typing import Any

_CAREER_MODES = frozenset({"career", "science"})
_MAX_CONTRACTS = 8
_MAX_PARAMS = 12
_MAX_PARTS = 60
_TEXT = 240


def sample_career(conn: Any) -> dict[str, Any]:
    """Return a career snapshot. Never raises; a miss is ``available`` false and a reason."""
    center = _center(conn)
    mode = _enum_name(_read(center, "game_mode"))
    snapshot: dict[str, Any] = {
        "mode": mode,
        "available": False,
        "reason": None,
        "funds": _num(center, "funds"),
        "science": _num(center, "science"),
        "reputation": _num(center, "reputation"),
        "offered": [],
        "active": [],
        "failed": [],
        "vessel_parts": [],
        "liquid_fuel": None,
        "oxidizer": None,
        "solid_fuel": None,
    }
    parts, fuels = _vessel_capability(center)
    snapshot["vessel_parts"] = parts
    snapshot["liquid_fuel"] = fuels.get("LiquidFuel")
    snapshot["oxidizer"] = fuels.get("Oxidizer")
    snapshot["solid_fuel"] = fuels.get("SolidFuel")
    if mode not in _CAREER_MODES:
        shown = mode or "unknown"
        snapshot["reason"] = (
            f"Game mode is {shown}. Career and science saves have contracts; this one does not."
        )
        return snapshot
    manager = _read(center, "contract_manager")
    if manager is None:
        snapshot["reason"] = "kRPC has no ContractManager on this save, so there is nothing to accept."
        return snapshot
    offered = _contract_list(manager, "offered_contracts")
    active = _contract_list(manager, "active_contracts")
    failed = _contract_list(manager, "failed_contracts")
    if offered is None or active is None:
        snapshot["reason"] = "ContractManager did not return offered and active contracts."
        return snapshot
    snapshot["available"] = True
    snapshot["offered"] = [_contract(item) for item in offered[:_MAX_CONTRACTS]]
    snapshot["active"] = [_contract(item) for item in active[:_MAX_CONTRACTS]]
    if failed is not None:
        snapshot["failed"] = [_contract(item, with_parameters=False) for item in failed[:_MAX_CONTRACTS]]
    return snapshot


def _center(conn: Any) -> Any:
    try:
        return getattr(conn, "space_center", None)
    except Exception:
        return None


def _read(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    try:
        return getattr(obj, name)
    except Exception:
        return None


def _contract_list(manager: Any, name: str) -> list[Any] | None:
    value = _read(manager, name)
    if value is None:
        return None
    try:
        if callable(value):
            value = value()
    except Exception:
        return None
    if value is None:
        return []
    try:
        return list(value)
    except TypeError:
        return None


def _contract(contract: Any, *, with_parameters: bool = True) -> dict[str, Any]:
    state = _enum_name(_read(contract, "state")) or "unknown"
    raw: dict[str, Any] = {
        "type": _clip(_read(contract, "type")) or "contract",
        "title": _clip(_read(contract, "title")) or "Untitled contract",
        "state": state,
        "description": _clip(_read(contract, "description")),
        "synopsis": _clip(_read(contract, "synopsis")),
        "notes": _clip(_read(contract, "notes")),
        "funds_advance": _num(contract, "funds_advance"),
        "funds_completion": _num(contract, "funds_completion"),
        "funds_failure": _num(contract, "funds_failure"),
        "reputation_completion": _num(contract, "reputation_completion"),
        "reputation_failure": _num(contract, "reputation_failure"),
        "science_completion": _num(contract, "science_completion"),
        "parameters": [],
    }
    if with_parameters:
        raw["parameters"] = _parameters(contract)
    return raw


def _parameters(contract: Any) -> list[dict[str, Any]]:
    nodes = _read(contract, "parameters")
    if nodes is None:
        return []
    try:
        if callable(nodes):
            nodes = nodes()
        pending = list(nodes)
    except TypeError:
        return []
    except Exception:
        return []
    leaves: list[dict[str, Any]] = []
    while pending and len(leaves) < _MAX_PARAMS:
        node = pending.pop(0)
        children = _read(node, "children")
        child_list: list[Any] = []
        if children is not None:
            try:
                child_list = list(children() if callable(children) else children)
            except TypeError:
                child_list = []
        if child_list:
            pending = child_list + pending
            continue
        title = _clip(_read(node, "title"))
        if not title:
            continue
        leaves.append(
            {
                "title": title,
                "notes": _clip(_read(node, "notes")),
                "completed": _bool(node, "completed") or False,
                "failed": _bool(node, "failed") or False,
                "optional": _bool(node, "optional") or False,
            }
        )
    return leaves


def _vessel_capability(center: Any) -> tuple[list[str], dict[str, float | None]]:
    fuels: dict[str, float | None] = {"LiquidFuel": None, "Oxidizer": None, "SolidFuel": None}
    vessel = _read(center, "active_vessel")
    if vessel is None:
        return [], fuels
    titles: list[str] = []
    parts = _read(vessel, "parts")
    all_parts = _read(parts, "all") if parts is not None else None
    try:
        if callable(all_parts):
            all_parts = all_parts()
        for part in list(all_parts or []):
            title = _clip(_read(part, "title"), 80) or _clip(_read(part, "name"), 80)
            if title and title not in titles:
                titles.append(title)
            if len(titles) >= _MAX_PARTS:
                break
    except TypeError:
        titles = []
    resources = _read(vessel, "resources")
    for name in fuels:
        fuels[name] = _resource_amount(resources, name)
    return titles, fuels


def _resource_amount(resources: Any, name: str) -> float | None:
    if resources is None:
        return None
    amount = _read(resources, "amount")
    if callable(amount):
        try:
            value = amount(name)
        except Exception:
            value = None
        else:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
    all_res = _read(resources, "all")
    try:
        if callable(all_res):
            all_res = all_res()
        for resource in list(all_res or []):
            if _clip(_read(resource, "name")) == name:
                return _num(resource, "amount")
    except TypeError:
        return None
    return None


def _clip(value: Any, limit: int = _TEXT) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text:
        return None
    return text[:limit]


def _enum_name(value: Any) -> str | None:
    if value is None:
        return None
    name = getattr(value, "name", None)
    if isinstance(name, str) and name and name != "name":
        return name.strip().lower()
    text = str(value).strip()
    if not text or text.startswith("<"):
        return None
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    text = text.strip().lower()
    return text or None


def _num(obj: Any, name: str) -> float | None:
    value = _read(obj, name)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _bool(obj: Any, name: str) -> bool | None:
    value = _read(obj, name)
    if isinstance(value, bool):
        return value
    return None
