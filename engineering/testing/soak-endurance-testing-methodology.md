# soak-endurance-testing-methodology

**Issue:** The service passes every load test — 15 minutes at peak traffic, p95 within budget — yet after three days in production it slows to a crawl, the container hits its memory limit, and connection pools quietly exhaust. The bugs responsible (slow leaks, unbounded caches, file-handle drift, connection accumulation, log-rotation stalls) are invisible at short durations because they are rate problems, not load problems: they only become observable on a trend line over hours. This article covers how to design, run, instrument, and act on soak/endurance tests, informed by Grafana's k6 soak-testing guidance, the 2026 OneUptime soak-testing guide, and practitioners running 4–24 hour endurance tests against .NET and JVM services.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Designing the soak profile

1. **Soak at realistic steady load, not peak.** Grafana's k6 guidance is explicit: ramp up to an average number of virtual users/throughput, then hold that level for a "considerably long duration" — typically 4–12 hours minimum, 24+ for release-critical services. Peak load belongs to stress tests; the soak exists to expose drift over time, and drift shows up at normal traffic.
2. **Choose the duration from the cleanup cycles you suspect, not from convenience.** A GC that only runs a full collection under pressure, a cache that only evicts after N hours of TTL misses, a cron that rotates logs nightly — the soak must span the longest periodic cycle in the system. A 6-hour soak cannot catch a leak that only manifests across a midnight boundary job.
3. **Include the traffic mix, not just the hot path.** Endurance bugs hide in the 1% of requests that leak (the export endpoint that streams and never closes, the error path that allocates and retains). Weight scenarios to production ratios so rare-but-leaky paths execute hundreds of times over the run.
4. **Warm up before you start measuring.** JIT compilation, connection-pool filling, and cache priming all cause early memory and latency noise; ramp up, hold 10–15 minutes, and only then begin the measurement window. Comparing a cold-start window to a steady-state window produces false positives on both sides.

## Instrumentation: what to record and how to read it

1. **Record resource counters at a fixed interval for the whole run — the trend is the assertion.** Resident memory, open file descriptors, socket counts, thread count, connection-pool utilization, and GC pause times, sampled every 30–60 seconds. A soak test without a time-series of these is just an expensive load test; the .NET soak-testing walkthroughs on k6 work precisely because memory is graphed, not averaged.
2. **Distinguish a sawtooth from a staircase.** Healthy memory under a GC looks like a sawtooth (allocate, collect, repeat at a stable amplitude); a leak looks like a staircase where each collection floor is higher than the last. Assert on the slope of the collection floors (the trend line), never on peak memory, which a legitimate cache can legitimately grow.
3. **Watch secondary resources that leak before memory does.** File descriptors and ephemeral ports usually exhaust first and are cheap to sample; `lsof` counts, `netstat` state counts, and pool `in-use` gauges often diagnose the leak class hours before the OOM kill would have.
4. **Capture latency as percentiles over time windows, not as a run-wide aggregate.** A run-wide p95 hides the degradation curve — the whole point of the soak. Compare p95 for the first hour against the last hour; a monotonic rise with flat CPU is the classic leak signature (more GC pressure or longer lookup chains).
5. **Correlate with internal metrics, not just container-level ones.** External memory tells you THAT you leak; the process's own metrics (cache entry counts, in-flight request gauges, queue depths, session counts) tell you WHERE. Export them over the same scrape interval so the graphs line up on one timeline.

## Running soaks without burning the team

1. **Schedule soaks; do not run them per-PR.** A 4–12 hour run cannot gate a merge. Trigger soaks on a cadence (nightly for the core service, pre-release for major versions, on-demand when a leak is suspected in production) — this is the same split used for mutation and full-load suites (see `mutation-testing-survivor-triage.md`).
2. **Run in a production-like but disposable environment.** Same runtime version, same limits (memory caps especially — cgroup limits change GC behavior), same config; but ephemeral, torn down after the run. A soak against a long-lived shared staging box is contaminated by everything else that has leaked into it.
3. **Add hard watchdogs so failures page at the moment of failure, not after 12 silent hours.** Alert when memory crosses 85% of the container limit, when fd count crosses a threshold, or when last-hour p95 exceeds first-hour p95 by more than X% — then abort and snapshot. Heap dumps and core dumps captured at the moment of exhaustion are diagnostic gold; ones captured after a restart are worthless.
4. **Keep a golden baseline per service and diff against it.** "Memory slope < X MB/hour and fd count flat" encoded as a budget turns the soak from an eyeballing exercise into a pass/fail artifact; store the baseline alongside the service config and update it deliberately, the same ratchet pattern as coverage and performance gates.
5. **Compress suspected leaks into short regression tests.** Once a leak is root-caused (e.g., a listener never unregistered), reproduce the retention loop directly — a unit or 5-minute integration test that executes the leaking path thousands of times and asserts the retained-object count stays flat. Practitioners explicitly recommend converting soak findings into short regression scenarios so the fix is locked in without re-running the marathon.

## Triage when the soak fails

1. **Confirm it reproduces before debugging.** Re-run with the same profile and seed data; approximately 30% of first-run "leaks" are artifacts of a contaminated environment, a concurrent deploy mid-run, or a monitoring gap. A leak that does not reproduce on a clean box was probably not your leak.
2. **Classify by trend shape.** Staircase memory = retained references (leaked listeners, unbounded caches, closures capturing scope); flat memory but climbing latency = degradation without retention (index bloat, fragmented pools, growing lock contention); climbing fds/sockets = unclosed resources under an error path; sawtooth with growing amplitude = GC thrash under a legitimate-but-growing working set.
3. **Take the differential heap dump.** Two heap snapshots — one after warmup, one at end of run — diffed by object type and retention path is the fastest root-cause tool; the count delta ranks suspects directly. For .NET use dotMemory/dotTrace-style tooling attached to the soak run; for JVM, `jmap`/JFR at the two sample points.
4. **Check the error paths first.** Endurance leaks disproportionately live in the unhappy paths that short functional tests never exercise at volume: retry logic that accumulates, compensating transactions that never fire, dead-letter handlers that retain payloads, metrics labels with unbounded cardinality (per-request label values are a notorious slow leak).

## Related

- `stress-testing-patterns.md` — short-duration overload behavior, the complement of endurance
- `load-test-scenarios.md` — scenario design that soak profiles reuse at reduced intensity
- `memory-leak-testing.md` — heap-diff techniques at unit scale
- `performance-regression-gates-ci.md` — encoding the soak's slope budgets as automated gates
