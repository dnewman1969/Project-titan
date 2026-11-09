# Installer

Windows NSIS installer built by `electron-builder` (D16). Arrives in M10.T4.

- `build-python.ps1` stages embedded CPython 3.12 and runs `uv sync --frozen` into `resources/python`.
- `build-pgsql.ps1` stages the portable PostgreSQL 16 binaries fetched by `tools/fetch-third-party.py`.
- `first-run/` holds the wizard step definitions (Ollama, OBS, Memurai, model pull, game integrations).

The CI `build-installer` job currently produces an unsigned NSIS build of the desktop shell only.

Local smoke before a release cut:

```powershell
pnpm build
pnpm --filter @titan/desktop dist
```

`dist` still packages the desktop shell; `build-python.ps1` / `build-pgsql.ps1` stage embedded
runtime assets in M10.T4.
