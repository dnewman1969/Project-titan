"""Adapter and discovery errors."""


class GameNotConnected(Exception):
    """The game or telemetry plugin is not reachable; the host should reconnect with backoff."""
