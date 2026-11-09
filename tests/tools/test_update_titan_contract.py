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


def test_update_titan_bat_invokes_powershell_once() -> None:
    raw = (ROOT / "Update-Titan.bat").read_bytes().decode("ascii", errors="strict")
    assert "-ExecutionPolicy" in raw
    assert "ecutionPolicy" not in raw.replace("-ExecutionPolicy", "")
    for line in raw.splitlines():
        if "ExecutionPolicy" in line or "powershell" in line.lower():
            assert "\r" not in line.strip()[:-1]  # no embedded CR mid-line
            assert "-ExecutionPolicy Bypass" in raw or ("TITAN_PS" in raw and "ExecutionPolicy Bypass" in raw)
    assert "TITAN_PS" in raw
    assert "System32\\WindowsPowerShell" in raw


def test_update_titan_ps1_does_not_respawn_powershell_for_start() -> None:
    text = (ROOT / "Update-Titan.ps1").read_text(encoding="utf-8")
    assert "& $startScript" in text
    assert "powershell -NoProfile -ExecutionPolicy Bypass -File $startScript" not in text
