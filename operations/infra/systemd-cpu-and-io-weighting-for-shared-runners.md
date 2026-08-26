# systemd CPU and I/O weighting for shared runners

**Issue:** Parallel jobs on a self-hosted runner can monopolize CPU or storage bandwidth, making critical services and independent checks slow or unreliable.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Place runner services and job scopes in deliberate systemd resource-control groups. Use relative controls such as `CPUWeight=` and `IOWeight=` to distribute contested capacity among sibling cgroups, and use hard quotas or limits only when a tested ceiling is required.

Weights matter only when resources are contested and depend on the relevant cgroup controller being available and enabled. I/O controls also depend on the storage stack and device accounting. A configuration accepted by systemd is not proof that the intended isolation is effective.

## Operational controls

- Keep runner jobs separate from control-plane, monitoring, and host-maintenance services.
- Apply changes first to a canary runner pool with representative compilation, test, container, and cache workloads.
- Reserve enough resources for the runner daemon to report status and terminate jobs.
- Pair concurrency limits with cgroup controls; weights do not prevent memory exhaustion.
- Use systemd drop-ins under configuration management and record the rationale for each value.
- Inspect effective cgroup settings after daemon reload and service restart.

## Verification

1. Confirm the host uses the expected cgroup mode and that CPU and I/O controllers are active.
2. Inspect service properties and the created cgroup hierarchy.
3. Run competing workloads and measure throughput, latency, CPU pressure, and I/O pressure.
4. Verify critical services remain responsive under full runner concurrency.
5. Test rollback of the drop-in and document the known-good baseline.

## Sources

- [systemd.resource-control](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html)
- [Linux kernel: Control Group v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)
- [Linux kernel: PSI](https://docs.kernel.org/accounting/psi.html)
