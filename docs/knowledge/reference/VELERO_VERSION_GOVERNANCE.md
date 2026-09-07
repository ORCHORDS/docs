---
title: Velero Backup and Disaster Recovery Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: Velero project (vmware-tanzu/velero); CNCF graduated; Velero documentation at velero.io
---

# Velero Backup and Disaster Recovery Version Governance

## Overview

This card governs how `orchords-docs` evaluates Velero across versions, CRD APIs, plugin compatibility, and disaster recovery posture. It is the canonical reference for any KB card that cites Kubernetes cluster backup, namespace restore, volume snapshotting, or cross-cluster migration.

Velero is a CNCF graduated project maintained by VMware Tanzu. It performs cluster resource backup, namespace-scoped restore, persistent-volume snapshotting through pluggable backends, and disaster recovery orchestration. This card treats Velero as a controlled dependency: version pins, plugin matrix, and Restic/Kopia/Data Mover selection are decided centrally and inherited by all dependent cards.

## Versioning model

- Semantic versioning: `MAJOR.MINOR.PATCH`. Minor releases ship on a roughly three-month cadence; patch releases are reserved for security and bug fixes.
- The Velero project advertises N-1 support: the current minor and the immediately preceding minor receive backports. Anything older is unsupported upstream.
- API versioning uses `velero.io/v1` for `Backup`, `Restore`, `Schedule`, `BackupStorageLocation`, and `VolumeSnapshotLocation`. The legacy `velero.io/v1beta1` API was removed prior to the current release line.
- Plugin versioning follows Velero's own version stream: each plugin release is tied to a compatible Velero minor, and mixing across minors is not supported.
- Upgrade window: ≤ 90 days after a new minor for production clusters; ≤ 14 days for security releases.

## Compatibility matrix

| Velero | Released | Status | Kubernetes tested | Notes |
|---|---|---|---|---|
| 1.16.x | mid-2026 | current | 1.30 – 1.33 | Data Mover GA; Kopia default |
| 1.15.x | early-2026 | N-1 | 1.29 – 1.32 | security fixes only |
| 1.14.x | late-2025 | N-2 | 1.28 – 1.31 | legacy; no backports |
| 1.13.x | mid-2025 | EoL | 1.27 – 1.30 | EoL |

References: `https://github.com/vmware-tanzu/velero/releases`, `https://velero.io/docs/`.

## Upgrade strategy

1. Read the upstream upgrade guide and the release notes for every minor jump; identify plugin API changes and CRD upgrades.
2. Apply CRD upgrades first, then the controller, then revalidate plugin digests.
3. Upgrade one Velero minor at a time; never skip minors.
4. Run a test backup and test restore in a staging cluster with the same CSI/storage topology as production before promoting.
5. Validate that all `BackupStorageLocation` and `VolumeSnapshotLocation` objects are `Available` after the upgrade before resuming schedules.
6. Roll back by reinstalling the prior Velero version; CRD downgrades are supported within the same `v1` API surface.

## CSI snapshot support

CSI snapshots are the preferred path for persistent-volume protection on any CSI-provisioned storage class:

- Enable the `csi-volumesnapshot` restore helper so PVCs are recreated from `VolumeSnapshotContent` rather than re-provisioned.
- Confirm the CSI driver exposes the `CRD: volumesnapshots.snapshot.storage.k8s.io` resources and a `Snapshot` class is bound.
- Treat `VolumeSnapshotLocation` as a thin compatibility layer: when CSI is available, prefer CSI snapshots over Velero-native snapshots for portability across clusters.
- Watch for `csiProvisioner` drift after driver upgrades; re-run a test backup to confirm PVC restoration paths.

## Restic vs Kopia vs Data Mover

Velero supports three file-level and data-movement paths; selection is policy:

- Restic: legacy file-level backup of pod volumes via a sidecar; retained for legacy clusters; no new feature work.
- Kopia: the default file-level backup since 1.13; faster, supports incremental restore, and is the recommended path for greenfield deployments.
- Data Mover: GA in 1.15+; moves snapshot data asynchronously to the object store, decoupling restore speed from cluster storage. Use Data Mover for large PVCs (> 500 GiB) or when restore latency must be predictable.
- Mixing Restic/Kopia within a single Velero install is supported per backup, but standardize on Kopia + Data Mover for new environments.

## Restore / DR posture

- Define RPO/RTO per namespace and reflect them in `Schedule` cadence and `BackupStorageLocation` placement.
- Test restore on a quarterly cadence in an isolated cluster; treat untested restores as a control deficiency.
- Use namespace-scoped restores (`--include-namespaces`) for application recovery; use the whole-cluster restore path only for declared disaster scenarios.
- Record restore drills and their elapsed time; surface in the change ticket and the post-restore review.
- Cross-cluster migration: install the same Velero version in the target cluster, point at the same `BackupStorageLocation`, and use `velero backup restore --from-backup` with `--preserve-scope` only when role bindings must survive.

## Backup security

- Encrypt backups at rest using the storage provider's SSE/KMS controls; never rely on bucket-default encryption alone.
- Restrict `BackupStorageLocation` credentials to least-privilege bucket roles; rotate access keys on the same cadence as cluster node credentials.
- Enable Velero's `server-side-restore` and disable anonymous `restic`/`kopia` repo URLs.
- Use RBAC to separate `backup` and `restore` principals: only break-glass roles should hold cluster-wide restore authority.
- Sign the Velero CLI binary and verify the SLSA provenance attestation before installation.

## Monitoring and alerting

Required metrics:

- `velero_backup_total_success{schedule}` and `velero_backup_total_failure{schedule}`.
- `velero_restore_total_success{restore}` and `velero_restore_total_failure{restore}`.
- `velero_backup_duration_seconds` histogram per schedule.
- `velero_pvc_snapshot_attempt_total{schedule,result}`.

One alert:

- `VeleroBackupStale` — page when a `Schedule` has not produced a successful `Backup` in `2 * schedule_interval + 30m`.
- `VeleroRestoreFailure` — page on `velero_restore_total_failure` for any restore older than 15 minutes with no compensating success.

References: `https://velero.io/docs/metrics/`, `https://github.com/vmware-tanzu/velero/blob/main/docs/metrics.md`.

## Review cadence

This card is reviewed every 180 days; the next scheduled review is 2027-03-07. The Knowledge Engineering owner re-validates the compatibility matrix, plugin list, and Restic/Kopia/Data Mover policy on each cycle and on every Velero minor release.

## References

- Velero docs: `https://velero.io/docs/`
- Velero repo: `https://github.com/vmware-tanzu/velero`
- Releases: `https://github.com/vmware-tanzu/velero/releases`
- Velero plugins: `https://github.com/vmware-tanzu/velero-plugin-for-aws`, `https://github.com/vmware-tanzu/velero-plugin-for-azure`, `https://github.com/vmware-tanzu/velero-plugin-for-gcp`
- CNCF Velero: `https://www.cncf.io/projects/velero/`
