# Linux pressure stall information as capacity signals

**Issue:** CPU utilization alone misses workloads stalled for memory reclaim or I/O, delaying diagnosis of overloaded hosts.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Linux Pressure Stall Information exposes CPU, memory, and I/O pressure through `/proc/pressure` and supported cgroup interfaces. `some` indicates at least some tasks stalled; `full` indicates all non-idle tasks stalled for the resource where defined.

Use PSI alongside latency, throughput, queue depth, utilization, and errors. Establish workload-specific baselines rather than copying universal thresholds.

## Controls

- Collect both averages and cumulative totals.
- Preserve cgroup labels without unbounded cardinality.
- Correlate pressure with application latency and OOM/reclaim events.
- Alert on sustained pressure, not isolated harmless bursts.
- Validate kernel and container visibility.
- Separate host-wide from service-level pressure.

## Verification

1. Generate controlled CPU, memory, and I/O contention.
2. Confirm the relevant PSI signal moves.
3. Correlate it with user-visible latency.
4. Verify recovery when contention ends.
5. Test alert timing against known saturation events.

## Sources

- [Linux kernel: Pressure Stall Information](https://docs.kernel.org/accounting/psi.html)
- [Linux kernel: cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)
