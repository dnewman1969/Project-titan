# Game adapter guide

How to add a game to Titan. The full guide is written in M10.T5 once the adapter SDK (M4.T1) exists.
Until then the contract is Section 2.10 of the [architecture spec](titan-architecture-spec.md):
a `titan-game.yaml` manifest, a `GameAdapter` subclass registered through a Python entry point,
declarative `events.yaml` rules (Section 7.5), and replay fixtures that the adapter test harness feeds
through the adapter in CI.
