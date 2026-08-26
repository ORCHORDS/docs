# Linux DAMON observation-overhead governance

**Issue:** Memory access profiling can consume enough CPU or generate enough trace data to distort the workload it is measuring.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Use the kernel DAMON sysfs interface only on kernels built with the required CONFIG_DAMON options. Start with coarse sampling, aggregation, region, and update intervals; narrow target address spaces; and separate passive observation from DAMOS actions that modify memory behavior. Establish CPU and memory overhead budgets before enabling traces or access-aware reclamation.

## Verification

Compare application latency, CPU, memory, and DAMON accuracy with monitoring off and at multiple interval settings. Test target exit, PID reuse, sysfs write failure, concurrent contexts, restart cleanup, and trace-buffer saturation.

## Gotchas

- Pin and verify exact platform versions before rollout.
- Preserve reproducible diagnostics without secrets or personal data.
- Define rollback and stop conditions before production use.

## Official source

- [Primary documentation](https://docs.kernel.org/admin-guide/mm/damon/)
