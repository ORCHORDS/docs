# cgroup v2 memory.high, memory.max, and OOM-group policy

**Issue:** A workload can cause host-wide reclaim stalls or kill unrelated processes when its memory boundary and OOM behavior are undefined.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

In cgroup v2, `memory.high` throttles and drives reclaim without being a hard ceiling, while `memory.max` is the ultimate limit. `memory.oom.group` can make an OOM kill apply to the workload as a unit. Size them from working-set measurements and recovery behavior.

## Controls and verification

- Leave host and supervisor headroom.
- Monitor current, events, pressure, swap, and OOM kills.
- Keep critical control processes outside a disposable job group.
- Test burst and sustained allocation separately.
- Coordinate application heap limits with cgroup limits.
- Load-test that throttling occurs before the intended hard-failure boundary and that service recovery is clean.

## Sources

- [Linux kernel: cgroup v2 memory controller](https://docs.kernel.org/admin-guide/cgroup-v2.html#memory)
- [Linux kernel: PSI](https://docs.kernel.org/accounting/psi.html)
