# titan-game-scs (shared)

Shared SCS Telemetry adapter for ETS2 and ATS (D13, Section 7.6). Reads the `Local\SCSTelemetry`
shared memory exposed by the pinned scs-sdk-plugin, using the versioned layout
`layouts/rencloud-1.12.yaml`, and refuses unknown plugin revisions. Arrives in M5.T3.
