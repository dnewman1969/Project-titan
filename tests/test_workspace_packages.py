"""Every uv workspace member is installed, importable and typed (Section 3)."""

from __future__ import annotations

import importlib
import tomllib
from importlib.resources import files
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MEMBERS = sorted(
    p.parent
    for pattern in ("packages/py/*/pyproject.toml", "services/*/pyproject.toml")
    for p in ROOT.glob(pattern)
)


def _module(member: Path) -> str:
    return next(p.name for p in member.iterdir() if p.is_dir() and p.name.startswith("titan_"))


def test_workspace_has_all_section_3_members() -> None:
    assert {m.name for m in MEMBERS} == {
        "titan-core",
        "titan-db",
        "titan-memory",
        "titan-models",
        "titan-sdk-games",
        "titan-testing",
        "api",
        "supervisor",
        "orchestrator",
        "telemetry",
        "capture",
        "workers",
        "actions",
    }


def test_root_project_depends_on_every_member() -> None:
    root = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    names = {
        tomllib.loads((m / "pyproject.toml").read_text(encoding="utf-8"))["project"]["name"] for m in MEMBERS
    }
    assert names <= set(root["tool"]["uv"]["sources"])


@pytest.mark.parametrize("member", MEMBERS, ids=lambda m: m.name)
def test_member_imports_and_ships_py_typed(member: Path) -> None:
    name = _module(member)
    module = importlib.import_module(name)
    assert module.__doc__
    assert files(name).joinpath("py.typed").is_file()
