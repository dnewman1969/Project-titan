"""Plugin install acceptance (M4): `uv pip install --target` registers `titan.games`."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def test_testgame_plugin_in_temp_target(tmp_path: Path) -> None:
    site_dir = tmp_path / "site-packages"
    uv = shutil.which("uv") or "uv"
    subprocess.run(  # noqa: S603
        [
            uv,
            "pip",
            "install",
            "--quiet",
            "--target",
            str(site_dir),
            str(REPO / "packages" / "py" / "titan-sdk-games"),
            str(REPO / "packages" / "py" / "titan-core"),
            str(REPO / "games" / "_testgame"),
        ],
        check=True,
        cwd=REPO,
    )
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, sys; sys.path.insert(0, os.environ['SITE']); "
            "from titan_sdk_games.loader import load_adapters; "
            "adapters = load_adapters(); "
            "assert 'testgame' in adapters; "
            "assert adapters['testgame'].load_manifest().id == 'testgame'",
        ],
        check=True,
        env={"SITE": str(site_dir)},
        cwd=REPO,
    )
    assert probe.returncode == 0
