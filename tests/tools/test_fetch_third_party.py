"""fetch-third-party tests (M0.T6). Downloads use file:// URLs, so no network is touched."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "titan_tools_fetch", ROOT / "tools" / "fetch-third-party.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["titan_tools_fetch"] = module
    spec.loader.exec_module(module)
    return module


fetch_tp = _load()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def artifact(tmp_path: Path, name: str, data: bytes, **extra: object) -> object:
    src = tmp_path / "upstream" / name
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(data)
    fields: dict[str, object] = {
        "id": name.split(".")[0].lower(),
        "name": name,
        "version": "1.0",
        "platform": "any",
        "url": src.as_uri(),
        "sha256": sha(data),
        "size": len(data),
        "archive": "zip" if name.endswith(".zip") else "none",
        "license": "MIT",
        "homepage": "https://example.invalid",
        "redistribute": True,
    }
    fields.update(extra)
    return fetch_tp.Artifact.model_validate(fields)


def test_repo_manifest_is_valid_and_pins_required_artifacts() -> None:
    manifest = fetch_tp.load_manifest(ROOT / "third_party" / "manifest.yaml")
    ids = {a.id for a in manifest.artifacts}
    assert {"postgresql", "ffmpeg", "presentmon", "krpc", "scs-sdk-plugin"} <= ids
    for a in manifest.artifacts:
        assert a.url.startswith("https://")
        assert len(a.sha256) == 64
    by_id = {a.id: a for a in manifest.artifacts}
    assert by_id["postgresql"].version.startswith("16.")
    assert by_id["ffmpeg"].version.startswith("7.")
    assert by_id["krpc"].version.startswith("0.5.")
    assert by_id["krpc"].redistribute is False


def test_fetch_verifies_and_caches(tmp_path: Path) -> None:
    a = artifact(tmp_path, "tool.exe", b"binary-bytes")
    cache = tmp_path / "cache"
    logs: list[str] = []
    path = fetch_tp.fetch(a, cache, logs.append)
    assert path.read_bytes() == b"binary-bytes"
    assert not list(cache.glob("*.part"))
    fetch_tp.fetch(a, cache, logs.append)
    assert "(cached)" in logs[-1]


def test_fetch_rejects_hash_mismatch(tmp_path: Path) -> None:
    good = artifact(tmp_path, "tool.exe", b"binary-bytes")
    tampered = good.model_copy(update={"sha256": sha(b"other-bytes")})
    cache = tmp_path / "cache"
    with pytest.raises(fetch_tp.VerificationError, match="sha256"):
        fetch_tp.fetch(tampered, cache, lambda _: None)
    assert not any(cache.iterdir())


def test_fetch_rejects_size_mismatch(tmp_path: Path) -> None:
    a = artifact(tmp_path, "tool.exe", b"binary-bytes")
    with pytest.raises(fetch_tp.VerificationError, match="size"):
        fetch_tp.fetch(a.model_copy(update={"size": 3}), tmp_path / "cache", lambda _: None)


def test_stale_cache_is_replaced(tmp_path: Path) -> None:
    a = artifact(tmp_path, "tool.exe", b"binary-bytes")
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "tool.exe").write_bytes(b"corrupted")
    logs: list[str] = []
    assert fetch_tp.fetch(a, cache, logs.append).read_bytes() == b"binary-bytes"
    assert logs[0].startswith("stale")


def test_refuses_plain_http(tmp_path: Path) -> None:
    a = artifact(tmp_path, "tool.exe", b"x").model_copy(update={"url": "http://example.invalid/tool.exe"})
    with pytest.raises(fetch_tp.VerificationError, match="non-HTTPS"):
        fetch_tp.fetch(a, tmp_path / "cache", lambda _: None)


def test_extract_verifies_inner_files(tmp_path: Path) -> None:
    dll = b"dll-bytes"
    data = make_zip({"pkg/Win64/plugin.dll": dll, "pkg/readme.txt": b"hi"})
    a = artifact(tmp_path, "plugin.zip", data, files=[{"path": "pkg/Win64/plugin.dll", "sha256": sha(dll)}])
    cache = tmp_path / "cache"
    dest = fetch_tp.extract(a, fetch_tp.fetch(a, cache, lambda _: None), cache)
    assert (dest / "pkg" / "Win64" / "plugin.dll").read_bytes() == dll

    bad = a.model_copy(update={"files": [fetch_tp.InnerFile(path="pkg/Win64/plugin.dll", sha256=sha(b"x"))]})
    with pytest.raises(fetch_tp.VerificationError, match=r"plugin\.dll"):
        fetch_tp.extract(bad, cache / "plugin.zip", cache)
    missing = a.model_copy(update={"files": [fetch_tp.InnerFile(path="pkg/nope.dll", sha256=sha(b"x"))]})
    with pytest.raises(fetch_tp.VerificationError, match="missing"):
        fetch_tp.extract(missing, cache / "plugin.zip", cache)


def test_extract_rejects_path_traversal(tmp_path: Path) -> None:
    data = make_zip({"../evil.txt": b"x"})
    a = artifact(tmp_path, "evil.zip", data)
    cache = tmp_path / "cache"
    with pytest.raises(fetch_tp.VerificationError, match="unsafe path"):
        fetch_tp.extract(a, fetch_tp.fetch(a, cache, lambda _: None), cache)
    assert not (tmp_path / "evil.txt").exists()


def test_extract_copies_plain_files(tmp_path: Path) -> None:
    a = artifact(tmp_path, "tool.exe", b"exe")
    cache = tmp_path / "cache"
    dest = fetch_tp.extract(a, fetch_tp.fetch(a, cache, lambda _: None), cache)
    assert (dest / "tool.exe").read_bytes() == b"exe"


def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a = artifact(tmp_path, "tool.exe", b"exe")
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        yaml.safe_dump({"schema_version": 1, "artifacts": [a.model_dump(exclude_defaults=True)]}),
        encoding="utf-8",
    )
    cache = tmp_path / "cache"
    assert fetch_tp.main(["--manifest", str(manifest), "--cache", str(cache), "--list"]) == 0
    assert "tool" in capsys.readouterr().out
    assert fetch_tp.main(["--manifest", str(manifest), "--cache", str(cache), "--extract"]) == 0
    assert (cache / "tool" / "tool.exe").is_file()
    assert fetch_tp.main(["--manifest", str(manifest), "--cache", str(cache), "nope"]) == 2
    tampered = tmp_path / "upstream" / "tool.exe"
    tampered.write_bytes(b"EXE")
    (cache / "tool.exe").unlink()
    assert fetch_tp.main(["--manifest", str(manifest), "--cache", str(cache)]) == 1


def test_manifest_rejects_duplicates(tmp_path: Path) -> None:
    a = artifact(tmp_path, "tool.exe", b"exe").model_dump(exclude_defaults=True)
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(yaml.safe_dump({"schema_version": 1, "artifacts": [a, a]}), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        fetch_tp.load_manifest(manifest)
