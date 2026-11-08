"""Layered configuration loaded into one typed `TitanConfig` (Section 9.5).

Precedence, lowest to highest:

1. `config/titan.yaml` shipped with the app (defaults).
2. The user's override file, `%APPDATA%/Titan/config/titan.yaml`.
3. The `settings` table (UI-edited values), passed in as a nested dict by the caller.
4. Environment variables `TITAN__<SECTION>__<KEY>`, e.g. `TITAN__API__PORT=8765`.
5. CLI flags, passed in as a nested dict.

Unknown keys fail at startup. Secrets never live in these files: they come from the OS
keyring (M1) or, for development and CI, from environment variables.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

ENV_PREFIX = "TITAN__"
CONFIG_DIR_ENV = "TITAN_CONFIG_DIR"
APP_CONFIG_FILE = "titan.yaml"


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ApiConfig(_Section):
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    # Renderer origins allowed to read API responses (Section 9.6). The packaged app is served
    # from app://titan; the dev shell adds its Vite origin when it launches the API.
    cors_origins: list[str] = ["app://titan"]


ServiceMode = Literal["managed", "external"]
"""`managed`: the supervisor runs the server. `external`: someone else does; health-check only."""


class PostgresConfig(_Section):
    host: str = "127.0.0.1"
    port: int = Field(default=54329, ge=1, le=65535)
    database: str = "titan"
    user: str = "titan"
    # Development and CI only. Otherwise the superuser password lives in the OS keyring as
    # 'titan/postgres', generated on first run (M1.T1).
    password: SecretStr | None = None
    mode: ServiceMode = "managed"
    data_dir: str = "%LOCALAPPDATA%/Titan/data/pg"
    # Directory with initdb/pg_ctl. Unset: the bundled or third_party/ copy, then pg_config.
    bin_dir: str | None = None

    def sqlalchemy_url(self, driver: str = "asyncpg") -> str:
        from urllib.parse import quote

        auth = quote(self.user, safe="")
        if self.password is not None:
            auth += ":" + quote(self.password.get_secret_value(), safe="")
        return f"postgresql+{driver}://{auth}@{self.host}:{self.port}/{quote(self.database, safe='')}"


class RedisConfig(_Section):
    url: str = "redis://127.0.0.1:63790/0"
    # Development and CI only. Otherwise `requirepass` comes from the OS keyring as 'titan/redis'.
    password: SecretStr | None = None


class ChromaConfig(_Section):
    host: str = "127.0.0.1"
    port: int = Field(default=8766, ge=1, le=65535)
    mode: ServiceMode = "managed"
    data_dir: str = "%LOCALAPPDATA%/Titan/data/chroma"
    # Server command before `run ...`. Unset: `chroma` from the venv or PATH, else `uvx` (dev).
    command: list[str] | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


class PathsConfig(_Section):
    recordings_root: str = "%USERPROFILE%/Videos/Titan"


class TelemetryConfig(_Section):
    publish_hz: float = Field(default=10, gt=0)
    sample_hz: float = Field(default=1, gt=0)
    chunk_minutes: int = Field(default=5, gt=0)


class AgentsConfig(_Section):
    tick_interval_ms: int = Field(default=10000, ge=2000)
    max_open_tasks_per_agent: int = Field(default=2, ge=1)
    context_token_budget: int = Field(default=3000, gt=0)


class DirectorConfig(_Section):
    tick_s: int = Field(default=15, gt=0)
    report_interval_s: int = Field(default=300, gt=0)
    can_spawn: bool = False


class FloorConfig(_Section):
    min_gap_ms: int = Field(default=1500, ge=0)
    max_words: int = Field(default=30, gt=0)
    idle_invite_s: int = Field(default=45, gt=0)
    arbitration_ms: int = Field(default=300, ge=0)


class LlmConfig(_Section):
    max_tokens_per_minute: int = Field(default=12000, gt=0)
    stale_drop_ms: int = Field(default=3000, gt=0)


class RecordingConfig(_Section):
    default_preset: str = "1080p60"
    min_free_gb: int = Field(default=20, ge=0)


class SafetyConfig(_Section):
    kill_hotkey: str = "Ctrl+Shift+F12"


class LoggingConfig(_Section):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    llm_prompts: bool = False


class NetworkConfig(_Section):
    offline_mode: bool = False
    allowlist_file: str = "config/egress.yaml"


ProcessName = Literal["postgres", "redis", "chroma", "migrate", "api"]
SUPERVISED_PROCESSES: tuple[ProcessName, ...] = ("postgres", "redis", "chroma", "migrate", "api")


class SupervisorConfig(_Section):
    host: str = "127.0.0.1"
    port: int = Field(default=8769, ge=1, le=65535)
    # Start order (Section 2.3). Each step waits up to start_timeout_s for health, then moves on.
    processes: list[ProcessName] = list(SUPERVISED_PROCESSES)
    start_timeout_s: float = Field(default=20, gt=0)

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


class MetricsConfig(_Section):
    sample_hz: float = Field(default=1, gt=0, le=10)
    # PresentMon console executable. Unset: the bundled or third_party/ copy, then PATH.
    presentmon_path: str | None = None
    nvml: bool = True


class OtelConfig(_Section):
    enabled: bool = False


class FeaturesConfig(_Section):
    research: bool = False
    factory: bool = False
    actions: bool = False
    tts: bool = False
    video: bool = False
    publish: bool = False


class TitanConfig(BaseSettings):
    """The whole Titan configuration. Use `load_config()` to build one."""

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="forbid",
        frozen=True,
    )

    api: ApiConfig = ApiConfig()
    postgres: PostgresConfig = PostgresConfig()
    redis: RedisConfig = RedisConfig()
    chroma: ChromaConfig = ChromaConfig()
    paths: PathsConfig = PathsConfig()
    telemetry: TelemetryConfig = TelemetryConfig()
    agents: AgentsConfig = AgentsConfig()
    director: DirectorConfig = DirectorConfig()
    floor: FloorConfig = FloorConfig()
    llm: LlmConfig = LlmConfig()
    recording: RecordingConfig = RecordingConfig()
    safety: SafetyConfig = SafetyConfig()
    logging: LoggingConfig = LoggingConfig()
    network: NetworkConfig = NetworkConfig()
    supervisor: SupervisorConfig = SupervisorConfig()
    metrics: MetricsConfig = MetricsConfig()
    otel: OtelConfig = OtelConfig()
    features: FeaturesConfig = FeaturesConfig()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Constructor kwargs are only used by load_config() for CLI flags (highest).
        # File and settings-table layers are supplied through _LayeredConfig below.
        return (init_settings, env_settings)


class _DictSource(PydanticBaseSettingsSource):
    def __init__(self, settings_cls: type[BaseSettings], data: Mapping[str, Any]) -> None:
        super().__init__(settings_cls)
        self._data = dict(data)

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return self._data.get(field_name), field_name, False

    def __call__(self) -> dict[str, Any]:
        return self._data


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge `override` into a copy of `base`."""
    out: dict[str, Any] = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def read_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML mapping. A missing or empty file yields `{}`."""
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    return data


def find_app_config_dir(start: Path | None = None) -> Path:
    """Locate the shipped `config/` directory.

    `TITAN_CONFIG_DIR` wins. Otherwise search upwards from `start` (default: the current
    directory, then this file) for a `config/titan.yaml`.
    """
    env_dir = os.environ.get(CONFIG_DIR_ENV)
    if env_dir:
        return Path(env_dir)
    roots = [start] if start is not None else [Path.cwd(), Path(__file__).resolve().parent]
    for root in roots:
        for candidate in (root, *root.parents):
            if (candidate / "config" / APP_CONFIG_FILE).is_file():
                return candidate / "config"
    raise FileNotFoundError("could not find config/titan.yaml; set TITAN_CONFIG_DIR")


_WIN_VAR = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")


def _fallback_dir(name: str) -> str | None:
    home = Path.home()
    fallbacks = {
        "LOCALAPPDATA": home / ".local" / "share",
        "APPDATA": home / ".config",
        "USERPROFILE": home,
        "PROGRAMDATA": Path("/var/lib"),
    }
    path = fallbacks.get(name.upper())
    return None if path is None else str(path)


def expand_path(value: str) -> Path:
    """Expand `%VAR%` placeholders used in config paths.

    On Windows the real environment variable is used. Elsewhere (CI, Linux development)
    well-known Windows folders fall back to XDG-style locations under the home directory.
    """

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        found = os.environ.get(name) or _fallback_dir(name)
        if found is None:
            raise KeyError(f"environment variable {name} is not set")
        return found

    return Path(_WIN_VAR.sub(repl, value)).expanduser()


def user_config_file() -> Path:
    """`%APPDATA%/Titan/config/titan.yaml`."""
    return expand_path("%APPDATA%/Titan/config/titan.yaml")


def load_config(
    *,
    app_config_dir: Path | None = None,
    user_config: Path | Literal[False] | None = None,
    db_settings: Mapping[str, Any] | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
) -> TitanConfig:
    """Build the effective `TitanConfig` from every layer (see module docstring).

    `user_config=None` uses the default per-user file; pass `False` to skip that layer.
    """
    app_dir = app_config_dir if app_config_dir is not None else find_app_config_dir()
    layers = [read_yaml(app_dir / APP_CONFIG_FILE)]
    if user_config is not False:
        layers.append(read_yaml(user_config if user_config is not None else user_config_file()))
    if db_settings:
        layers.append(dict(db_settings))
    base: dict[str, Any] = {}
    for layer in layers:
        base = deep_merge(base, layer)

    class _LayeredConfig(TitanConfig):
        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            return (init_settings, env_settings, _DictSource(settings_cls, base))

    layered = _LayeredConfig(**dict(cli_overrides or {}))
    return TitanConfig.model_construct(**{name: getattr(layered, name) for name in TitanConfig.model_fields})
