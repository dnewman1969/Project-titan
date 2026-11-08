"""Secrets in the OS keyring: Windows Credential Manager (DPAPI) through `keyring` (Section 2.8).

Entries live under service `titan` (override with `TITAN_KEYRING_SERVICE`, used by tests) with
the secret's name as the user name: `titan/postgres`, `titan/redis`. Secrets never go in config
files, Postgres or logs. Development and CI may instead pass them as `TITAN__<SECTION>__PASSWORD`.
"""

from __future__ import annotations

import os
import secrets as _random

import keyring
import keyring.errors
from pydantic import SecretStr

SERVICE_ENV = "TITAN_KEYRING_SERVICE"
DEFAULT_SERVICE = "titan"


class SecretStoreUnavailable(RuntimeError):
    """No usable OS keyring (typical on headless Linux). Set the secret through the environment."""


def service_name() -> str:
    return os.environ.get(SERVICE_ENV) or DEFAULT_SERVICE


def get_secret(name: str) -> str | None:
    try:
        return keyring.get_password(service_name(), name)
    except keyring.errors.NoKeyringError as exc:
        raise SecretStoreUnavailable(str(exc)) from exc


def set_secret(name: str, value: str) -> None:
    try:
        keyring.set_password(service_name(), name, value)
    except keyring.errors.NoKeyringError as exc:
        raise SecretStoreUnavailable(str(exc)) from exc


def delete_secret(name: str) -> None:
    try:
        keyring.delete_password(service_name(), name)
    except keyring.errors.PasswordDeleteError:
        pass
    except keyring.errors.NoKeyringError as exc:
        raise SecretStoreUnavailable(str(exc)) from exc


def resolve_secret(configured: SecretStr | None, name: str) -> SecretStr | None:
    """The configured value if set, else the keyring entry, else None (also when no keyring)."""
    if configured is not None:
        return configured
    try:
        value = get_secret(name)
    except SecretStoreUnavailable:
        return None
    return None if value is None else SecretStr(value)


def generate_password() -> str:
    """32 random bytes, URL-safe, so it can go in connection strings without quoting."""
    return _random.token_urlsafe(32)
