"""Keyring-backed secrets (Section 2.8) against an in-memory backend."""

from __future__ import annotations

from collections.abc import Iterator

import keyring
import keyring.backend
import keyring.errors
import pytest
from keyring.backends.fail import Keyring as FailKeyring
from pydantic import SecretStr

from titan_core import secrets


class MemoryKeyring(keyring.backend.KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.entries: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.entries.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.entries[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if self.entries.pop((service, username), None) is None:
            raise keyring.errors.PasswordDeleteError(username)


@pytest.fixture
def memory() -> Iterator[MemoryKeyring]:
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture
def no_keyring() -> Iterator[None]:
    previous = keyring.get_keyring()
    keyring.set_keyring(FailKeyring())
    yield
    keyring.set_keyring(previous)


def test_round_trip_under_the_titan_service(memory: MemoryKeyring, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(secrets.SERVICE_ENV, raising=False)
    secrets.set_secret("postgres", "pw")
    assert memory.entries == {("titan", "postgres"): "pw"}
    assert secrets.get_secret("postgres") == "pw"
    secrets.delete_secret("postgres")
    secrets.delete_secret("postgres")
    assert secrets.get_secret("postgres") is None


def test_service_override(memory: MemoryKeyring, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(secrets.SERVICE_ENV, "titan-test-123")
    secrets.set_secret("redis", "pw")
    assert ("titan-test-123", "redis") in memory.entries


def test_resolve_prefers_configured_value(memory: MemoryKeyring) -> None:
    secrets.set_secret("redis", "from-keyring")
    assert secrets.resolve_secret(SecretStr("from-env"), "redis") == SecretStr("from-env")
    resolved = secrets.resolve_secret(None, "redis")
    assert resolved is not None and resolved.get_secret_value() == "from-keyring"
    assert secrets.resolve_secret(None, "missing") is None


@pytest.mark.usefixtures("no_keyring")
def test_unavailable_keyring() -> None:
    with pytest.raises(secrets.SecretStoreUnavailable):
        secrets.get_secret("postgres")
    with pytest.raises(secrets.SecretStoreUnavailable):
        secrets.set_secret("postgres", "pw")
    with pytest.raises(secrets.SecretStoreUnavailable):
        secrets.delete_secret("postgres")
    assert secrets.resolve_secret(None, "postgres") is None


def test_generated_passwords_are_long_and_url_safe() -> None:
    first, second = secrets.generate_password(), secrets.generate_password()
    assert first != second
    assert len(first) >= 43
    assert all(c.isalnum() or c in "-_" for c in first)
