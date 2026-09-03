# Maintenance Automation Must Use PDB-Aware Eviction

**Issue:** Maintenance automation deletes pods directly and therefore bypasses the availability policy operators expected a PodDisruptionBudget to enforce.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

Kubernetes documents API-initiated eviction as the policy-controlled path for voluntary pod removal. Evictions respect configured PodDisruptionBudgets and graceful termination settings. Direct deletion is not an interchangeable maintenance primitive when disruption policy matters.

## Engineering rule

- Use the Eviction API, or tooling such as `kubectl drain` that uses it, for voluntary maintenance where PDBs are part of the availability contract.
- Treat an eviction refusal as a safety signal to investigate capacity or policy rather than immediately switching to direct deletion.
- Reserve forced/direct deletion for explicitly approved exceptional recovery paths with separate risk handling.

## Verification

- Create a restrictive PDB and prove maintenance automation is blocked when eviction would violate it.
- Inspect the automation path to confirm it creates eviction requests rather than unconditional pod deletes.
- Test termination grace behavior and application shutdown hooks during maintenance.

## Official sources

- Kubernetes API-initiated Eviction: https://kubernetes.io/docs/concepts/scheduling-eviction/api-eviction/
- Kubernetes disruptions and PodDisruptionBudgets: https://kubernetes.io/docs/concepts/workloads/pods/disruptions/
