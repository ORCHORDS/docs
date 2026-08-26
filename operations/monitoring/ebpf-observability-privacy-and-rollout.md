# ebpf-observability-privacy-and-rollout

**Issue:** eBPF-based observability is enabled broadly without an event budget, privacy model, kernel-compatibility plan, or rollback procedure.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

A platform adds kernel-level visibility to troubleshoot networking or workload behavior. Telemetry volume, label cardinality, PII exposure, CPU overhead, or an incompatible node kernel then creates a production incident.

## Root cause

eBPF provides deep runtime observation, but it is not a zero-cost or privacy-neutral logging mechanism. A safe rollout must constrain what is captured, who can access it, which kernels and agents are supported, and how collection is disabled under load.

**Source:** [Cilium Hubble observability documentation](https://docs.cilium.io/en/stable/observability/hubble/).

## Fix

- define the concrete questions the telemetry must answer before enabling probes;
- minimize captured fields, redact identifiers where possible, and apply bounded retention;
- enforce cardinality budgets and sample high-volume event classes;
- certify supported kernel, agent, and CNI versions in a staged environment;
- publish resource guardrails and alerts for agent CPU, memory, dropped events, and exporter backlog;
- deploy progressively by node pool with a tested disable/rollback path.

## Verification

- A representative investigation is possible without collecting request bodies or unnecessary identifiers.
- Load testing stays within the agreed overhead budget.
- Unsupported nodes are detected before rollout.
- Disabling the collector restores baseline behavior without disrupting application traffic.

## Gotchas

- More telemetry is not automatically better telemetry; high-cardinality labels can destabilize the monitoring backend.
- Kernel-level visibility does not replace application authorization logs or audit trails.
- Access to raw flow data is sensitive and needs role-based controls.

## Related

- `infra/cilium-vs-calico-2026.md`
- `patterns/observability-three-pillars.md`
- `security/audit-log.md`
