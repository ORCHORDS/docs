# PodDisruptionBudgets Protect Voluntary Disruptions, Not Every Failure

**Issue:** A team treats a Kubernetes PodDisruptionBudget as a general high-availability guarantee and assumes it prevents simultaneous pod loss from any cause.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

Kubernetes PodDisruptionBudgets limit how many replicas of an application may be unavailable during voluntary disruptions. They do not make involuntary failures impossible and should not be used as evidence that node loss, crashes, resource exhaustion, or other failure modes are covered.

## Engineering rule

- Size replica counts and topology for involuntary failure independently of the PDB.
- Use the PDB to express the minimum availability expected during voluntary maintenance and eviction.
- Validate readiness semantics because PDB availability decisions depend on pod health state.
- Test failure scenarios separately from maintenance/drain scenarios.

## Verification

- Drain a node through a PDB-respecting path and confirm the availability budget is enforced.
- Separately simulate an involuntary replica or node failure and confirm the service still meets its availability design without relying on the PDB.
- Check quorum-based systems against actual quorum math, not only `minAvailable` labels.

## Official sources

- Kubernetes disruptions and PodDisruptionBudgets: https://kubernetes.io/docs/concepts/workloads/pods/disruptions/
- Kubernetes PodDisruptionBudget API: https://kubernetes.io/docs/reference/kubernetes-api/policy/pod-disruption-budget-v1/
