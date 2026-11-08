"""Import-boundary lint (Sections 6.9, 9.7 and 10).

1. import-linter contracts from `.importlinter` beside this file: services never import each other,
   packages never import services, input libraries only in titan-actions, HTTP only via titan_core.http.
2. An AST scan that import-linter cannot do: no `SendInput`/`keybd_event`/`mouse_event` access and
   no input-library imports anywhere outside `services/actions` (this also covers games/ and tools/).

    uv run python tools/lint-imports/run.py
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CONFIG = HERE / ".importlinter"
SCAN_DIRS = ("packages", "services", "games", "tools")
ALLOWED_DIRS = (Path("services") / "actions",)
SKIP_PARTS = frozenset({".venv", "node_modules", "__pycache__", "dist", "out"})
INPUT_FUNCS = frozenset({"SendInput", "keybd_event", "mouse_event"})
INPUT_LIBS = frozenset({"pyautogui", "vgamepad", "pydirectinput"})


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path.as_posix()}:{self.line}: {self.message}"


def iter_python_files(root: Path) -> Iterator[Path]:
    for top in SCAN_DIRS:
        base = root / top
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(root)
            if SKIP_PARTS.intersection(rel.parts):
                continue
            if any(rel.is_relative_to(allowed) for allowed in ALLOWED_DIRS):
                continue
            yield path


def check_source(source: str, path: Path) -> list[Violation]:
    violations: list[Violation] = []
    for node in ast.walk(ast.parse(source, filename=str(path))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in INPUT_LIBS:
                    violations.append(Violation(path, node.lineno, f"input library import '{alias.name}'"))
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0 and node.module.split(".")[0] in INPUT_LIBS:
                violations.append(Violation(path, node.lineno, f"input library import '{node.module}'"))
            for alias in node.names:
                if alias.name in INPUT_FUNCS:
                    violations.append(Violation(path, node.lineno, f"input function import '{alias.name}'"))
        elif isinstance(node, ast.Attribute) and node.attr in INPUT_FUNCS:
            violations.append(Violation(path, node.lineno, f"input function access '.{node.attr}'"))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in INPUT_FUNCS
        ):
            violations.append(
                Violation(path, node.lineno, f"input function access getattr '{node.args[1].value}'")
            )
    return violations


def scan(paths: Iterable[Path], root: Path) -> list[Violation]:
    found: list[Violation] = []
    for path in paths:
        found.extend(check_source(path.read_text(encoding="utf-8"), path.relative_to(root)))
    return found


def run_import_linter(config: Path = CONFIG) -> int:
    from importlinter.cli import lint_imports

    return lint_imports(
        config_filename=str(config), cache_dir=str(ROOT / ".import_linter_cache"), no_logo=True
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--ast-only", action="store_true", help="skip import-linter contracts")
    args = parser.parse_args(argv)

    violations = scan(iter_python_files(ROOT), ROOT)
    for violation in violations:
        print(violation, file=sys.stderr)
    status = 1 if violations else 0
    if violations:
        print(
            f"{len(violations)} input choke-point violation(s); move this code to services/actions.",
            file=sys.stderr,
        )
    else:
        print("AST input choke-point scan: OK")
    if not args.ast_only and run_import_linter() != 0:
        status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
