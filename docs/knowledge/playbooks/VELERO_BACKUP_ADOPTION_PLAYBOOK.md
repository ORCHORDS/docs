# Velero Backup Adoption Playbook

## Purpose

Adopt Velero for namespace-scoped and cluster-wide backup and restore in Kubernetes clusters, with safe upgrade cadence, Restic/Kopia file-system posture, and CSI snapshot handling. The playbook keeps restore time observable and reversible so disaster recovery exercises are reproducible.

## Audience

Platform engineers, SREs, security engineers, and DR coordinators responsible for cluster data protection and restore testing.

## Pre-conditions

- Velero version pinned per `docs/knowledge/reference/VELERO_VERSION_GOVERNANCE.md`.
- Object storage bucket configured (S3, GCS, Azure Blob, or MinIO) with a dedicated prefix per cluster.
- IAM role, IRSA, or Workload Identity credentials configured for the Velero service account; no static access keys.
- Restic-vs-Kopia decision recorded (Kopia is the default unless a workload has been validated against Restic).
- CSI snapshot CRDs installed (`snapshot.storage.k8s.io`) and a matching `VolumeSnapshotClass` available for every storage class in scope.
- A sandbox namespace approved for restore drills.

## Procedure

### Step 1 — Install Velero via Helm

1. Add the `vmware-tanzu` Helm repository and pin the chart version from `VELERO_VERSION_GOVERNANCE.md`.
2. Render values: enable the metrics endpoint, set the namespace, set the `credentials` secret name, and toggle the file-system backup plugin (`restic` or `kopia`).
3. Install with `helm install velero vmware-tanzu/velero -n velero -f values.yaml`.
4. Confirm the deployment is Ready and the metrics Service is reachable.

### Step 2 — Configure storage locations

5. Create a `BackupStorageLocation` per cluster pointing at the object storage bucket and prefix; set `spec.config.syncFrequency` to a 1-hour interval.
6. Create one `VolumeSnapshotLocation` per region or storage class; pin `spec.provider` and `spec.config` per cloud.
7. Validate with `velero backup-location get` and `velero snapshot-location get`; both must report `Available`.

### Step 3 — Define schedules

8. Author a daily namespace schedule (`schedule=@daily`, label selector to scope) and a weekly cluster-wide schedule (`schedule=@weekly`, include cluster resources).
9. Add a `ttl` of at least 30 days for the daily schedule and 90 days for the weekly schedule.
10. Configure `orderedResources` and `excludeNamespaces` for stateful workloads that should not run during business hours.

### Step 4 — Test restore into a sandbox namespace

11. Take a manual backup of a non-production namespace: `velero backup create drill-<ts> --include-namespaces <ns>`.
12. Restore into a sandbox namespace with a remapped name: `velero restore create drill-restore-<ts> --from-backup drill-<ts> --namespace-mappings <ns>:<ns>-restore`.
13. Confirm pods reach Ready, PVCs are bound, and Service endpoints resolve.
14. Record the restore duration in the change ticket and attach `velero describe restore` output.

### Step 5 — Configure hooks for stateful workloads

15. Annotate stateful workloads with `pre.hook.backup.velero.io` and `post.hook.restore.velero.io` for quiesce / unfreeze behavior.
16. Order hooks so that databases quiesce before the backup hook runs and unfreeze after the restore hook completes.
17. Validate hook ordering with a dry-run restore against a disposable StatefulSet replica.

### Step 6 — Adopt cluster-wide

18. Move from the daily namespace schedule to the weekly cluster-wide schedule for production namespaces.
19. Wire the Velero Prometheus metrics into the cluster dashboard and alert on `velero_backup_failure_total` and `velero_backup_last_success_timestamp_seconds`.
20. Schedule a quarterly restore drill and link the output to the DR runbook.

## Rollback

- Helm uninstall path: `helm uninstall velero -n velero`; CRDs are retained by default so existing backup metadata in object storage remains valid.
- Apply the `BackupStorageLocation` retention policy before deletion so orphaned backup objects are reaped by TTL, not by hand.
- For a partial restore that lands in the wrong namespace, delete the restored PVCs and pods with `kubectl delete` filtered by the restore label, then re-run the restore with corrected mappings.
- If Velero cannot talk to object storage, suspend schedules (`velero schedule pause`) and page on-call before re-enabling.
- Never delete a `BackupStorageLocation` until the associated backups have been verified restorable into a sandbox.

## References

- `docs/knowledge/reference/VELERO_VERSION_GOVERNANCE.md`
- Velero backup and restore docs: `https://velero.io/docs/main/backup/`
- Velero CSI snapshot docs: `https://velero.io/docs/main/csi/`
- Velero hooks: `https://velero.io/docs/main/hooks/`
