# Ceph RGW Multi-site Disaster Recovery Playbook

## Purpose

Establish and rehearse an active-active or active-passive RADOS Gateway (RGW) multi-site deployment for S3-compatible object storage, including failover, failback, and consistency verification.

## Audience

Storage engineers, SRE on-call, disaster-recovery coordinators.

## Pre-conditions

- Two Ceph clusters (primary and secondary) running Reef 18.2.x or later, connected via low-latency inter-site link.
- `radosgw-admin` CLI ≥ Reef on a workstation with admin caps.
- Zone groups configured in **active-active** mode (multi-master) or **active-passive** mode (single-master with archive zone).
- Replication policy documented: `replicate-transactionally` (synchronous) or `replicate-async` (best-effort).

## Procedure

### 1. Initial multi-site bootstrap

1. On the primary zone, create the realm, zonegroup, and zone:
   `radosgw-admin realm create --rgw-realm=prod --default`
   `radosgw-admin zonegroup create --rgw-realm=prod --rgw-zonegroup=us --master --default`
   `radosgw-admin zone create --rgw-realm=prod --rgw-zonegroup=us --rgw-zone=us-1 --master --default`
2. Pull the zone configuration and pull-period/system-flag on the secondary cluster; create the secondary zone without `--master`.
3. Verify bidirectional replication with `radosgw-admin sync status --source-zone=us-1`.

### 2. Continuous replication

- Primary zone writes are forwarded to the secondary within the configured `sync_from_all` window.
- Monitor `radosgw_sync_data_changes_total{zone,status}` and `radosgw_sync_status{direction}`.
- Alert on `radosgw_sync_status{direction="out"} > threshold_seconds` (default 60 s) — investigate before secondary drift exceeds 5 minutes.

### 3. Failover (active-passive)

1. Demote primary zone with `radosgw-admin zone modify --rgw-zone=us-1 --master=false`.
2. Promote secondary on the alternate cluster with `radosgw-admin zone modify --rgw-zone=us-2 --master=true --default`.
3. Update DNS and S3 endpoint records to point at the secondary cluster's RGW endpoints.
4. Verify with `aws --endpoint-url <secondary> s3 ls` that objects are reachable.

### 4. Failback

- Reverse the demote/promote steps; perform a **full sync** of the secondary's writes back to the primary before re-promoting it.
- Validate bucket listing parity with `radosgw-admin bucket sync checkpoint --source-zone=us-2 --compare-buckets`.

### 5. Disaster (total primary loss)

1. Treat the surviving cluster as the new primary.
2. Re-bootstrap the lost cluster with empty zones and let it replicate from the survivor.
3. Reapply zonegroup and zone configuration; verify replication catches up.

## Rollback

- In active-passive mode, "rollback" means demote secondary, promote primary; no data loss as long as async replication lag was within the configured threshold.
- For active-active mismatches, use `radosgw-admin data sync status` to identify and reconcile divergent objects; never delete the secondary's data first.

## References

- Ceph RGW multi-site documentation — https://docs.ceph.com/en/latest/radosgw/multisite/
- Internal: Batch 99 reference card `CEPH_VERSION_GOVERNANCE.md`.
