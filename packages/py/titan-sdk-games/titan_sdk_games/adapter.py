"""`GameAdapter` ABC (Section 2.10.2)."""

from __future__ import annotations

import hashlib
import shutil
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, ClassVar

from titan_core.protocol.telemetry import TelemetryFrame
from titan_sdk_games.discovery.base import scan_all_stores
from titan_sdk_games.manifest import GameManifest
from titan_sdk_games.profiles import GameProfile
from titan_sdk_games.types import (
    Consent,
    ControlBindingDTO,
    DetectedInstall,
    DiscoveryContext,
    IntegrationStatus,
)


class NotSupported(Exception):
    """Phase 4 surface on a Phase 1 adapter."""


class RawFrame(dict[str, Any]):
    """Adapter-native telemetry frame before normalization."""


class AdapterConfig(dict[str, Any]):
    """Runtime configuration passed to connect()."""


class GameAdapter(ABC):
    """Base class for game plugins. Subclasses set `entry_point` and may cache `manifest`."""

    entry_point: ClassVar[str] = ""
    manifest: ClassVar[GameManifest | None] = None

    @classmethod
    def load_manifest(cls) -> GameManifest:
        cached = cls.__dict__.get("manifest")
        if isinstance(cached, GameManifest):
            return cached
        path = cls.manifest_path()
        manifest = GameManifest.from_yaml_path(path)
        cls.manifest = manifest
        return manifest

    @classmethod
    def manifest_path(cls) -> Path:
        raise NotImplementedError(f"{cls.__name__} must override manifest_path()")

    @abstractmethod
    async def connect(self, profile: GameProfile, cfg: AdapterConfig) -> None: ...

    @abstractmethod
    def normalize(self, raw: RawFrame) -> TelemetryFrame: ...

    @classmethod
    def detect(cls, ctx: DiscoveryContext, *, stores: list[str] | None = None) -> list[DetectedInstall]:
        manifest = cls.load_manifest()
        detection = manifest.detection
        store_list = stores if stores is not None else ["steam", "epic", "gog", "standalone"]
        installs = scan_all_stores(ctx, store_list)
        found: list[DetectedInstall] = []
        for inst in installs:
            if inst.store == "steam" and str(inst.app_id) not in {str(x) for x in detection.steam_app_ids}:
                continue
            if inst.store == "epic":
                epic_ids = {str(x) for x in detection.epic_catalog_ids}
                if inst.app_id not in epic_ids and (inst.name or "") not in epic_ids:
                    continue
            if inst.store == "gog" and str(inst.app_id) not in {str(x) for x in detection.gog_product_ids}:
                continue
            if inst.store == "standalone" and not _matches_executable(
                inst.executable_path, detection.executables
            ):
                continue
            found.append(
                DetectedInstall(
                    game_slug=manifest.id,
                    store=inst.store,
                    install_path=inst.install_path,
                    executable_path=inst.executable_path,
                    game_version=inst.build_id,
                    build_id=inst.build_id,
                    launch_uri=manifest.launch.steam_uri,
                )
            )
        return found

    def check_integration(self, profile: GameProfile) -> IntegrationStatus:
        manifest = self.load_manifest()
        telemetry = manifest.telemetry
        if not telemetry.requires_plugin or telemetry.plugin is None:
            return IntegrationStatus(status="installed", details={"required": None})
        target = Path(profile.install_path) / telemetry.plugin.install_to
        if not target.exists():
            return IntegrationStatus(
                status="missing",
                details={
                    "required": f"{telemetry.plugin.name} {telemetry.plugin.version}",
                    "found": None,
                },
                instructions_md=f"Install **{telemetry.plugin.name}** into `{telemetry.plugin.install_to}`.",
            )
        digest = _sha256_file(target)
        if digest.lower() != telemetry.plugin.sha256.lower() and not telemetry.plugin.sha256.startswith(
            "00000000"
        ):
            return IntegrationStatus(
                status="outdated",
                details={
                    "required": f"{telemetry.plugin.name} {telemetry.plugin.version}",
                    "found": digest,
                    "expected": telemetry.plugin.sha256,
                },
                instructions_md="Plugin hash mismatch; reinstall the pinned integration.",
            )
        return IntegrationStatus(
            status="installed",
            details={
                "required": f"{telemetry.plugin.name} {telemetry.plugin.version}",
                "found": digest,
            },
        )

    def install_integration(self, profile: GameProfile, consent: Consent) -> IntegrationStatus:
        if not consent.granted:
            return IntegrationStatus(status="failed", details={"reason": "consent_required"})
        before = self.check_integration(profile)
        if before.status == "installed":
            return before
        manifest = self.load_manifest()
        plugin = manifest.telemetry.plugin
        if plugin is None:
            return IntegrationStatus(status="installed")
        bundle = self.integration_bundle_path()
        if bundle is None or not bundle.is_file():
            return IntegrationStatus(
                status="missing",
                details={"reason": "bundle_unavailable"},
                instructions_md="Integration bundle is not available in this environment.",
            )
        target = Path(profile.install_path) / plugin.install_to
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundle, target)
        after = self.check_integration(profile)
        return after

    def integration_bundle_path(self) -> Path | None:
        """Optional pinned artifact shipped with the adapter package."""
        return None

    def parse_controls(self, profile: GameProfile) -> list[ControlBindingDTO]:
        from titan_sdk_games.parsers.ksp_settings import parse_ksp_settings_cfg
        from titan_sdk_games.parsers.scs_sii import parse_scs_controls_sii

        manifest = self.load_manifest()
        bindings: list[ControlBindingDTO] = []
        for spec in manifest.config_files:
            if spec.parser == "scs_sii":
                for path in _expand_profile_paths(profile.install_path, spec.path):
                    if path.is_file():
                        bindings.extend(parse_scs_controls_sii(path))
            if spec.parser == "ksp_settings":
                for path in _expand_profile_paths(profile.install_path, spec.path):
                    if path.is_file():
                        bindings.extend(parse_ksp_settings_cfg(path))
        defaults = self.default_controls_path()
        if defaults and defaults.is_file() and not bindings:
            bindings.extend(self._load_default_controls(defaults))
        del profile
        return bindings

    def default_controls_path(self) -> Path | None:
        manifest = self.load_manifest()
        root = self.manifest_path().parent
        candidate = root / manifest.controls_default
        return candidate if candidate.is_file() else None

    def _load_default_controls(self, path: Path) -> list[ControlBindingDTO]:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        out: list[ControlBindingDTO] = []
        for row in data:
            if isinstance(row, dict):
                out.append(ControlBindingDTO.model_validate({**row, "source": "default"}))
        return out

    async def disconnect(self) -> None:
        return None

    def frames(self) -> AsyncIterator[RawFrame]:
        raise NotImplementedError

    def detect_events(
        self,
        prev: TelemetryFrame | None,
        cur: TelemetryFrame,
        raw: RawFrame,
    ) -> list[Any]:
        del prev, cur, raw
        return []

    def scene(self, frame: TelemetryFrame) -> str:
        del frame
        return "unknown"

    def world_state_summary(self, frame: TelemetryFrame) -> dict[str, Any]:
        del frame
        return {}

    def default_team(self) -> dict[str, Any]:
        return {}

    def tools(self) -> list[Any]:
        return []

    def action_space(self) -> dict[str, Any]:
        raise NotSupported("action_space is Phase 4")

    async def execute(self, action: Any) -> Any:
        raise NotSupported("execute is Phase 4")


def _matches_executable(path: str, patterns: list[str]) -> bool:
    norm = Path(path).as_posix().lower()
    for pattern in patterns:
        if pattern.lower() in norm or Path(path).name.lower() == Path(pattern).name.lower():
            return True
    return False


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _expand_profile_paths(install_path: str, pattern: str) -> list[Path]:
    import os

    expanded = os.path.expandvars(pattern)
    if "*" in expanded:
        return [p for p in Path(expanded).parent.glob(Path(expanded).name) if p.is_file()]
    candidate = Path(install_path) / expanded
    if candidate.is_file():
        return [candidate]
    absolute = Path(expanded)
    if absolute.is_file():
        return [absolute]
    if "*" in pattern:
        return [p for p in Path(install_path).glob(pattern) if p.is_file()]
    return []
