# NATS Cluster Failover Playbook

## Purpose

Define the operational procedure for recovering a NATS cluster when one or more nodes fail. The procedure covers core NATS (no JetStream), JetStream persistence, and leafnode edges.

## Audience

Platform engineers, SREs, and on-call responders.

## Pre-conditions

- NATS 2.10+ (per `NATS_VERSION_GOVERNANCE.md`).
- The cluster has at least 3 nodes.
- JetStream is enabled if persistence is required.
- Monitoring emits cluster health events.

## Procedure

### Step 1 — Detect

1. Confirm cluster health: `nats server check connection -s nats://<host>:4222`.
2. Confirm peer list: `nats server list -s nats://<host>:4222`.
3. Confirm JetStream status (if enabled): `nats str list -s nats://<host>:4222`.

### Step 2 — Diagnose

4. Identify the failed node(s) via monitoring.
5. Inspect the failed node's logs (`stderr.log` or `journalctl`).
6. Determine root cause:
   - Process crash.
   - OOM.
   - Disk full.
   - Network partition.
   - Disk corruption (JetStream).

### Step 3 — Recover a single node

7. If the failed node is recoverable, restart it: `systemctl restart nats`.
8. Confirm the node rejoins the cluster.
9. Confirm quorum is restored.

### Step 4 — Recover a partition

10. If the cluster is partitioned, restore network access.
11. Confirm all nodes rejoin via gossip.
12. Confirm the leader is elected.

### Step 5 — Recover a JetStream node

13. If a JetStream node has disk corruption, quarantine the node.
14. Replace the disk.
15. Initialize the JetStream node with the same name.
16. Confirm the stream metadata rebalances.

### Step 6 — Recover from total loss

17. If the entire cluster is lost, restore from backup:
    - Streams are persisted under `${store_dir}/jetstream`.
    - `$JSZ` API or `nats str info` confirms restoration.
18. Reapply configuration from GitOps (per `GITOPS_SYNC_FAILURE_RECOVERY_PLAYBOOK.md`).

### Step 7 — Verify

19. Confirm all subjects are reachable.
20. Confirm JetStream consumers can resume.
21. Confirm cluster metrics return to baseline.

### Step 8 — Postmortem

22. File a postmortem per `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.
23. Identify the failure origin.
24. Add regression tests or guard rails.

## Rollback

If recovery introduces regressions:

1. Restore from backup.
2. Verify against pre-incident snapshots.

## References

- `NATS_VERSION_GOVERNANCE.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- NATS operations: `https://docs.nats.io/running-a-nats-service/nats_admin`
- JetStream disaster recovery: `https://docs.nats.io/nats-concepts/jetstream/disaster_recovery`
