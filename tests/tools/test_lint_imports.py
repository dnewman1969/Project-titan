"""Import-boundary lint tests: the rules must fail on violations, not only pass on clean code."""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "titan_tools_lint_imports", ROOT / "tools" / "lint-imports" / "run.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["titan_tools_lint_imports"] = module
    spec.loader.exec_module(module)
    return module


lint = _load()


@pytest.mark.parametrize(
    "source",
    [
        "import pyautogui",
        "import vgamepad as vg",
        "from pydirectinput import press",
        "import ctypes\nctypes.windll.user32.SendInput(1, None, 0)",
        "from ctypes import windll\nf = getattr(windll.user32, 'SendInput')",
        "import ctypes\nctypes.windll.user32.keybd_event(0, 0, 0, 0)",
        "from somewhere import mouse_event",
    ],
)
def test_ast_flags_input_access(source: str) -> None:
    assert lint.check_source(source, Path("x.py"))


@pytest.mark.parametrize(
    "source",
    [
        "import ctypes\nctypes.windll.user32.GetForegroundWindow()",
        "NAMES = {'SendInput'}",
        "from . import pyautogui_docs",
    ],
)
def test_ast_allows_unrelated_code(source: str) -> None:
    assert lint.check_source(source, Path("x.py")) == []


def test_scan_skips_actions_service(tmp_path: Path) -> None:
    bad = "import vgamepad\n"
    (tmp_path / "services" / "actions" / "titan_actions").mkdir(parents=True)
    (tmp_path / "services" / "actions" / "titan_actions" / "pad.py").write_text(bad)
    (tmp_path / "games" / "ets2").mkdir(parents=True)
    (tmp_path / "games" / "ets2" / "adapter.py").write_text(bad)
    (tmp_path / "packages" / ".venv").mkdir(parents=True)
    (tmp_path / "packages" / ".venv" / "lib.py").write_text(bad)
    found = lint.scan(lint.iter_python_files(tmp_path), tmp_path)
    assert [v.path.as_posix() for v in found] == ["games/ets2/adapter.py"]
    assert str(found[0]) == "games/ets2/adapter.py:1: input library import 'vgamepad'"


def test_repository_passes_ast_scan() -> None:
    assert lint.scan(lint.iter_python_files(ROOT), ROOT) == []


def test_contracts_break_on_violations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkgs = tmp_path / "src"
    for name, body in {
        "fake_svc_a": "import fake_svc_b\nimport httpx\n",
        "fake_svc_b": "",
    }.items():
        (pkgs / name).mkdir(parents=True)
        (pkgs / name / "__init__.py").write_text(body)
    monkeypatch.syspath_prepend(str(pkgs))
    config = tmp_path / ".importlinter"
    config.write_text(
        textwrap.dedent(
            """
            [importlinter]
            root_packages =
                fake_svc_a
                fake_svc_b
            include_external_packages = True

            [importlinter:contract:independent]
            name = independent
            type = independence
            modules =
                fake_svc_a
                fake_svc_b

            [importlinter:contract:http]
            name = http
            type = forbidden
            source_modules = fake_svc_a
            forbidden_modules = httpx
            allow_indirect_imports = True
            """
        )
    )
    monkeypatch.setattr(lint, "ROOT", tmp_path)
    assert lint.run_import_linter(config) == 1


def test_main_reports_ok(capsys: pytest.CaptureFixture[str]) -> None:
    assert lint.main(["--ast-only"]) == 0
    assert "OK" in capsys.readouterr().out
