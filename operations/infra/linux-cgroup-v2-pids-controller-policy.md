# Linux cgroup v2 PID-controller policy

**Issue:** Memory and CPU limits do not stop a workload from exhausting the host's task table through runaway forks or threads.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Enable the cgroup v2 `pids` controller at the correct parent and set `pids.max` from measured worker, thread-pool, sidecar, and burst demand with explicit headroom. Remember that the controller counts tasks, including threads, rather than only process-group leaders. Monitor `pids.current`, `pids.peak` where supported, and `pids.events`/`pids.events.local` limit hits instead of waiting for application symptoms.

Keep a host-level reserve for supervisors and recovery tools, and impose descendant-depth/count governance separately. Treat `fork()` or `clone()` returning `EAGAIN` as a capacity signal with a bounded application response, not an instruction to spin and retry. Coordinate the cgroup value with systemd `TasksMax=` or container-runtime limits so the effective ceiling is understood.

## Verification

Use a disposable cgroup to create processes and threads up to the limit, assert the next creation fails, and verify event counters and alerts. Test nested cgroups, raising and lowering the limit, moving existing tasks, supervisor recovery, and a workload whose normal peak includes many threads.

## Gotchas

- Organizational moves can make `pids.current` exceed `pids.max`; the policy blocks new task creation rather than killing existing tasks.
- A limit that is too low can block health checks or graceful shutdown helpers.
- cgroup v1 and v2 delegation semantics differ.

## Official source

- [Linux cgroup v2 PID controller](https://docs.kernel.org/admin-guide/cgroup-v2.html#pid)
