# titan-supervisor

Process supervisor (Section 2.3, M1.T1 to M1.T3 and M1.T6). Electron starts it with the launch token;
it starts `postgres, redis, chroma, migrate, api` in order, health-checks each, restarts crashed
children with backoff (1, 2, 4 … 30 s; circuit opens after 5 failures in 2 min), samples system
metrics at 1 Hz into `titan:sys:metrics`, and stops everything on quit.

| Module        | Purpose                                                                       |
| ------------- | ----------------------------------------------------------------------------- |
| `core.py`     | Start order, health loop, restart policy, event log                           |
| `units.py`    | Child processes (with descendant tracking), one-shot steps, external checks   |
| `postgres.py` | Portable PostgreSQL 16: `initdb` with a keyring password, `pg_ctl`, adoption  |
| `catalog.py`  | Builds the units from `supervisor.processes` in config                        |
| `metrics.py`  | psutil, NVML and PresentMon sampling                                          |
| `server.py`   | Supervisor RPC on 127.0.0.1:8769 (Section 5.2): status, restart, shutdown     |
| `winjob.py`   | Windows job object with KILL_ON_JOB_CLOSE so no child outlives the supervisor |
| `procutil.py` | Spawning (new process group, PDEATHSIG on Linux), tree termination            |

```powershell
$env:TITAN_LAUNCH_TOKEN = "dev-token"
uv run titan-supervisor
Invoke-RestMethod http://127.0.0.1:8769/status -Headers @{ Authorization = "Bearer $env:TITAN_LAUNCH_TOKEN" }
```

Tests: `uv run pytest services/supervisor` (fakes for the policy, real processes and a real
PostgreSQL 16 where the binaries exist) and `tests/integration/test_supervisor_e2e.py`.
