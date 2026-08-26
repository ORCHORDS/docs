# pytest-xdist work-stealing scheduler tradeoffs

**Issue:** Static test distribution leaves workers idle when test durations are uneven, but changing scheduling modes without checking isolation can introduce nondeterminism or fixture conflicts.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

pytest-xdist's `--dist=worksteal` scheduler initially assigns work across workers and transfers queued tests from workers with larger remaining queues to workers that are nearly done. Evaluate it when test duration skew creates a long tail after most workers become idle.

Scheduling does not make tests isolated. Tests must still avoid shared mutable databases, ports, files, accounts, clocks, and order assumptions. Collection must be consistent across workers, and fixtures with session scope execute in separate worker processes unless explicitly coordinated.

## Operational controls

- Establish correctness under serial execution before tuning parallel scheduling.
- Record per-test durations and worker utilization to prove that imbalance is the bottleneck.
- Cap worker count from measured CPU, memory, I/O, database, and service capacity rather than host CPU count alone.
- Allocate unique external resources from the xdist worker identity.
- Keep reruns separate from scheduling analysis so flakes do not masquerade as load-balancing gains.
- Preserve failure logs with worker identity and deterministic reproduction commands.

## Verification

1. Run the same suite serially and with the existing distribution mode.
2. Run repeated `worksteal` trials and compare wall time, utilization, failures, and result count.
3. Inject a few intentionally slow tests and verify idle time decreases.
4. Repeat failures serially and under a fixed worker count.
5. Confirm tests collected by all workers remain identical.

## Sources

- [pytest-xdist: Distribution modes](https://pytest-xdist.readthedocs.io/en/stable/distribution.html)
- [pytest-xdist: How it works](https://pytest-xdist.readthedocs.io/en/stable/how-it-works.html)
- [pytest: Good integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
