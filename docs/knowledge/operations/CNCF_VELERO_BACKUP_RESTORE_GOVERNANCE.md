# CNCF Velero Backup and Restore Governance

## Purpose

Govern the use of Velero for Kubernetes cluster backup and restore so that backups run on schedule, are verified restorable, and restore procedures are exercised rather than assumed, with retention and security controls matching the sensitivity of the data protected.

## Scope

Applies to every Velero-managed backup of studio Kubernetes clusters, covering schedules, retention, storage locations, restore procedures, and restore testing. It does not cover application-level data replication or database-specific backup tooling.

## Workflow

1. Define backup schedules per cluster based on change rate and recovery objectives: full or file-hourly incremental as appropriate, with the rationale documented.
2. Configure object storage locations with encryption at rest and access restricted to the backup service account; backup storage inherits the sensitivity of the data it holds.
3. Apply retention policies deliberately: retain enough history to cover the recovery point objectives and the rollback window; infinite retention is not a policy.
4. Capture both cluster resources and persistent volumes in backup scope; a resource-only backup is not a restore capability and must be labeled as such.
5. Run restore tests on a recurring cadence against an isolated namespace or cluster, with success criteria defined before each test.
6. Record every production restore as an event with scope, duration, and data-loss delta between last backup and incident time.
7. Upgrade Velero and plugins on a deliberate cadence, validating plugin compatibility with the storage backend before promotion.

## Controls and evidence

- Backup schedule definitions with rationale, scope (resources, volumes), and retention per cluster.
- Storage location configuration showing encryption and access restriction.
- Restore test records: date, scope, success criteria, result, and findings.
- Production restore event log with scope, duration, and data-loss delta.

## Validation

- Confirm the most recent backup for each production cluster completed within its schedule window.
- Confirm each cluster's restore test ran within its cadence and met its success criteria.
- Sample one backup and confirm both cluster resources and persistent volume data are included.

## Failure correction

- **Missed backup window** → run the backup immediately, determine the cause (credentials, storage quota, snapshot timeout), and fix the schedule or the cause.
- **Restore test fails** → open a finding, block the "restore-proven" status for that cluster, and fix before the cadence date passes again.
- **Retention drift (backups accumulating beyond policy)** → correct retention settings and review whether storage costs or delete protection drove the deviation.

## Limitations

- Velero snapshots at the volume level; application-consistent backups require pre/post hooks or application-level tooling for stateful workloads.
- Restore capability is proven by test; schedule success alone is not evidence of recoverability.
- Cross-provider restores depend on plugin support and volume migration; verify before relying on them.

## Scope note

This article is part of the operations leaf and pairs with disaster recovery and contingency guidance. Cross-reference: `infra/disaster-recovery-rto-rpo.md`, `itil-4-change-enablement-practice.md`, and `NIST_SP_800_34_CONTINGENCY_PLAN_TYPES_AND_EXERCISE` guidance at `nist-sp-800-34-contingency-plan-types-and-exercise.md`.

## Canonical sources

- Velero Documentation — Backup and restore: https://velero.io/docs/main/
- Velero Documentation — How Velero works: https://velero.io/docs/v1.14/how-velero-works/
- NIST SP 800-34 Rev 1 — Contingency Planning Guide: https://csrc.nist.gov/publications/detail/sp/800-34/rev-1/final
- NIST SP 800-209 — Security Guidelines for Storage Infrastructure: https://csrc.nist.gov/publications/detail/sp/800-209/final
- Kubernetes Documentation — Volume snapshots: https://kubernetes.io/docs/concepts/storage/volume-snapshots-kubernetes/
