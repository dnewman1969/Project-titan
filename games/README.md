# Games

One package per supported game (Section 2.10 and Section 7). Each holds a `titan-game.yaml` manifest,
an adapter, `events.yaml` rules, default controls, a Phase 1 team template and replay fixtures.
Fixtures larger than 5 MB are stored with Git LFS (`.gitattributes`).

| Folder        | Game                                                     | Arrives in                    |
| ------------- | -------------------------------------------------------- | ----------------------------- |
| `ksp/`        | Kerbal Space Program (kRPC, D12)                         | M4.T3 manifest, M5.T2 adapter |
| `scs-common/` | Shared SCS shared-memory adapter and layout parser (D13) | M5.T3                         |
| `ets2/`       | Euro Truck Simulator 2 (uses `scs-common`)               | M4.T3, M5.T3                  |
| `ats/`        | American Truck Simulator (uses `scs-common`)             | M4.T3, M5.T3                  |

See [`docs/game-adapter-guide.md`](../docs/game-adapter-guide.md).
