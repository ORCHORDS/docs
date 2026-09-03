# PodDisruptionBudget Maintenance Review Template

Use this record to verify that Kubernetes voluntary-maintenance automation respects PodDisruptionBudgets and that the PDB is not being treated as protection from involuntary failures.

## Review metadata

- Workload: `<name>`
- Namespace/environment class: `<non-sensitive identifier>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Controller and replica count: `<type/count>`

## Availability design

- PDB selector: `<selector summary>`
- `minAvailable` or `maxUnavailable`: `<value>`
- Application quorum/minimum serving replicas: `<value and rationale>`
- Readiness condition used by availability calculations: `<summary>`
- Involuntary-failure tolerance: `<separate design summary>`

## Maintenance-path checks

- [ ] Maintenance uses the Eviction API or tooling that respects it.
- [ ] An eviction that would violate the PDB is blocked and surfaced as a safety condition.
- [ ] Automation does not silently fall back to direct deletion.
- [ ] Graceful termination behavior is tested.
- [ ] Capacity exists to complete expected maintenance without violating the application requirement.

## Failure-mode checks

- [ ] Node/pod involuntary failure is tested separately from maintenance.
- [ ] Replica placement/topology supports the required failure tolerance.
- [ ] Quorum assumptions are validated against real application behavior.

## Evidence and findings

- Drain/eviction test: `<reference/result>`
- Involuntary-failure test: `<reference/result>`
- Findings: `<text>`
- Corrective actions/owner/date: `<text>`

## Sources

- Kubernetes disruptions and PodDisruptionBudgets: https://kubernetes.io/docs/concepts/workloads/pods/disruptions/
- Kubernetes API-initiated Eviction: https://kubernetes.io/docs/concepts/scheduling-eviction/api-eviction/
