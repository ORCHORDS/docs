# etcd Disaster Recovery Playbook

## Purpose

Recover an etcd cluster from data corruption, accidental deletion, quorum loss, or split-brain. The playbook covers snapshot restore, member replacement, and quorum restoration.

## Audience

Platform engineers, SRE on-call, Kubernetes operators, database operators.

## Pre-conditions

1. The reference card is current: `ETCD_VERSION_GOVERNANCE.md`.
2. `etcdctl snapshot save` is configured to run on a regular cadence (default every 4 hours).
3. Snapshots are stored in object storage (S3-compatible) with versioning.
4. Backup encryption is configured (AES-256).
5. The cluster name and initial cluster token are documented.

## Procedure

### 1. Detect disaster

Symptoms of an etcd disaster:

- `etcd_server_has_leader = 0` for ≥ 1 minute.
- Quorum loss (e.g., 3-node cluster with 2 nodes down).
- Persistent leader elections.
- Data corruption errors: `"etcdserver: mvcc: database space exceeded"`, `"compact: requested compaction revision is old"`.
- Application errors: Kubernetes API server `500`s, Patroni cluster split-brain.

### 2. Confirm disaster

1. Run `etcdctl endpoint status` from each member.
2. Check `etcdctl endpoint health` for the cluster.
3. Validate quorum: `etcdctl member list`.
4. Validate disk usage: `etcdctl disk usage` on each member.

### 3. Decide on recovery strategy

| Symptom | Recovery strategy |
|---|---|
| Single member down | replace member |
| Quorum loss, snapshot current | restore from snapshot |
| Quorum loss, snapshot stale | restore from snapshot + replay WAL |
| Data corruption | restore from snapshot |
| Accidental key deletion | restore from snapshot (last good snapshot) |

### 4. Recover from snapshot

1. Identify the most recent good snapshot from the backup store.
2. On a fresh node (or all nodes), run:
   ```bash
   etcdctl snapshot restore <snapshot> \
     --name <member-name> \
     --initial-cluster <initial-cluster> \
     --initial-advertise-peer-urls <peer-url> \
     --data-dir <data-dir>
   ```
3. Update the etcd cluster definition (static pod manifest for Kubernetes).
4. Start the new etcd member(s).
5. Validate quorum: `etcdctl endpoint status`.
6. Validate data: `etcdctl get / --prefix`.

### 5. Replace a single member

1. Remove the failed member from the cluster: `etcdctl member remove <id>`.
2. Add a new member: `etcdctl member add <name> --peer-urls <peer-url>`.
3. On the new member, configure the cluster membership.
4. Start the new member.
5. Validate quorum.

### 6. Restore on Kubernetes (kube-apiserver)

1. Stop the kube-apiserver pods.
2. Restore etcd from snapshot using `etcdctl snapshot restore`.
3. Update the etcd StatefulSet.
4. Restart kube-apiserver pods.
5. Validate: `kubectl get nodes`, `kubectl get pods --all-namespaces`.

### 7. Validate

- Quorum: `etcdctl endpoint status` shows all members healthy.
- Data integrity: `etcdctl get / --prefix --keys-only | wc -l` matches expectations.
- Application: API server / Patroni returns 200 OK.
- Replication: lag = 0.

### 8. Post-incident

1. Document the disaster cause and recovery actions in the change ticket.
2. Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.
3. Update backup frequency if needed.
4. Validate the recovery procedure quarterly.

## Rollback

Rollback of an etcd restore is possible if a previous snapshot is available. The procedure:

1. Stop the restored cluster.
2. Restore from a previous (older) snapshot.
3. Validate.
4. Update the audit log with the rollback event.

## Mandatory pre-flight (before adopting a new etcd deployment)

1. Backup cadence is configured.
2. Snapshot target is documented.
3. Backup encryption is configured.
4. Restore procedure is documented.
5. Restore is tested quarterly.

## Observability

- `etcd_server_has_leader` (gauge).
- `etcd_server_leader_changes_seen_total` (counter).
- `etcd_server_proposals_committed_total` (counter).
- `etcd_disk_backend_commit_duration_seconds` (histogram).
- `etcd_disk_backend_snapshot_duration_seconds` (histogram, per snapshot).

## References

- `ETCD_VERSION_GOVERNANCE.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- etcd disaster recovery: `https://etcd.io/docs/v3.5/op-guide/recovery/`
- etcd operator disaster recovery: `https://github.com/etcd-io/etcd-operator`
