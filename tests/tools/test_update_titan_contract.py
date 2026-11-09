"""Contract checks for Update-Titan.ps1 (Windows update entrypoint)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_update_titan_scripts_exist() -> None:
    assert (ROOT / "Update-Titan.bat").is_file()
    assert (ROOT / "Update-Titan.ps1").is_file()
    assert (ROOT / "Start-Titan.ps1").is_file()


def test_update_titan_documents_dirty_tree_and_pull_failures() -> None:
    text = (ROOT / "Update-Titan.ps1").read_text(encoding="utf-8")
    assert "Show-PullFailed" in text
    assert "Confirm-DiscardLocalChanges" in text
    assert "git pull --ff-only" in text
    assert "Test-DependencyInstallNeeded" in text
    assert "SkipDependencyInstall" in text


def test_start_titan_accepts_skip_dependency_install() -> None:
    text = (ROOT / "Start-Titan.ps1").read_text(encoding="utf-8")
    assert "SkipDependencyInstall" in text
    assert "param(" in text
