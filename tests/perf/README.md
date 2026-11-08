# Performance tests

Latency benchmarks (`pytest-benchmark` plus custom timers): bus throughput of 2,000 msgs/s or more and
event to first token with FakeProvider latency models. Regressions over 20% fail. They arrive with
the bus in M6 and are tuned in M10.T3.
