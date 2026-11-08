"""Download and verify the pinned third-party binaries in `third_party/manifest.yaml` (M0.T6).

    uv run python tools/fetch-third-party.py --list
    uv run python tools/fetch-third-party.py                   # everything into third_party/cache/
    uv run python tools/fetch-third-party.py postgresql ffmpeg --extract

Every download is streamed to a `.part` file, checked against the pinned size and SHA-256, and
only then renamed into place. A mismatch deletes the file and exits non-zero. Files already in
the cache are re-hashed instead of downloaded again.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import urllib.request
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "third_party" / "manifest.yaml"
DEFAULT_CACHE = ROOT / "third_party" / "cache"
CHUNK = 1024 * 1024
USER_AGENT = "ProjectTitan-fetch-third-party/1"

Sha256 = str


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InnerFile(_Strict):
    path: str
    sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    install_to: str | None = None


class Artifact(_Strict):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    version: str
    platform: str
    url: str
    sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(gt=0)
    archive: Literal["zip", "none"]
    license: str
    homepage: str
    redistribute: bool
    install: Literal["bundled", "user_consent"] = "bundled"
    notes: str | None = None
    files: list[InnerFile] = []
    used_by: list[str] = []

    @property
    def filename(self) -> str:
        name = PurePosixPath(urlparse(self.url).path).name
        if not name or name in {".", ".."}:
            raise ValueError(f"{self.id}: cannot derive a file name from {self.url}")
        return name


class Manifest(_Strict):
    schema_version: Literal[1]
    artifacts: list[Artifact]

    def select(self, ids: Sequence[str]) -> list[Artifact]:
        if not ids:
            return list(self.artifacts)
        known = {a.id: a for a in self.artifacts}
        missing = [i for i in ids if i not in known]
        if missing:
            raise KeyError(f"unknown artifact id(s): {', '.join(missing)}")
        return [known[i] for i in ids]


class VerificationError(Exception):
    pass


def load_manifest(path: Path) -> Manifest:
    manifest = Manifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    ids = [a.id for a in manifest.artifacts]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate artifact ids in manifest")
    return manifest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def verify(path: Path, artifact: Artifact) -> None:
    size = path.stat().st_size
    if size != artifact.size:
        raise VerificationError(f"{artifact.id}: size {size} != pinned {artifact.size}")
    actual = sha256_file(path)
    if actual != artifact.sha256:
        raise VerificationError(f"{artifact.id}: sha256 {actual} != pinned {artifact.sha256}")


def _download(artifact: Artifact, target: Path) -> None:
    scheme = urlparse(artifact.url).scheme
    if scheme not in {"https", "file"}:
        raise VerificationError(f"{artifact.id}: refusing non-HTTPS url {artifact.url}")
    request = urllib.request.Request(artifact.url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    part = target.with_name(target.name + ".part")
    with urllib.request.urlopen(request, timeout=60) as response, part.open("wb") as out:  # noqa: S310
        shutil.copyfileobj(response, out, CHUNK)
    try:
        verify(part, artifact)
    except VerificationError:
        part.unlink(missing_ok=True)
        raise
    part.replace(target)


def fetch(artifact: Artifact, cache: Path, log: Callable[[str], None] = print) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / artifact.filename
    if target.is_file():
        try:
            verify(target, artifact)
            log(f"ok      {artifact.id} {artifact.version} (cached)")
            return target
        except VerificationError as exc:
            log(f"stale   {artifact.id}: {exc}; downloading again")
            target.unlink()
    log(f"fetch   {artifact.id} {artifact.version} <- {artifact.url}")
    _download(artifact, target)
    log(f"ok      {artifact.id} {artifact.version} sha256={artifact.sha256[:12]}...")
    return target


def extract(artifact: Artifact, archive: Path, cache: Path) -> Path:
    """Extract a zip into `<cache>/<id>/` (rejecting path traversal) and verify pinned inner files."""
    dest = cache / artifact.id
    if artifact.archive != "zip":
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archive, dest / archive.name)
        return dest
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    root = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            out = (dest / member.filename).resolve()
            if root not in out.parents and out != root:
                raise VerificationError(f"{artifact.id}: unsafe path in archive: {member.filename}")
        zf.extractall(dest)
    for inner in artifact.files:
        path = dest / inner.path
        if not path.is_file():
            raise VerificationError(f"{artifact.id}: missing {inner.path} in archive")
        actual = sha256_file(path)
        if actual != inner.sha256:
            raise VerificationError(f"{artifact.id}: {inner.path} sha256 {actual} != pinned {inner.sha256}")
    return dest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("ids", nargs="*", help="artifact ids to fetch (default: all)")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--extract", action="store_true", help="also extract archives into <cache>/<id>/")
    parser.add_argument("--list", action="store_true", help="list artifacts and exit")
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    try:
        selected = manifest.select(args.ids)
    except KeyError as exc:
        print(f"error: {exc.args[0]}", file=sys.stderr)
        return 2
    if args.list:
        for a in selected:
            print(f"{a.id:16} {a.version:10} {a.license:32} {a.size / 1e6:8.1f} MB  {a.url}")
        return 0
    try:
        for artifact in selected:
            path = fetch(artifact, args.cache)
            if args.extract:
                print(f"extract {artifact.id} -> {extract(artifact, path, args.cache)}")
    except VerificationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
