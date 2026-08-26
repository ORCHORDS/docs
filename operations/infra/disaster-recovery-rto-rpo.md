# disaster-recovery-rto-rpo

**Issue:** Designing and actually testing disaster recovery against explicit RTO/RPO targets — instead of discovering during the incident that "we have backups" is not a recovery plan
**Date:** 2026-08-13
**Status:** documented

## Symptom / Context
An outage or region event hits and the questions surface one by one, each unanswered: How much data did we lose (RPO)? How long until we serve customers again (RTO)? Who declares the disaster? Where is the runbook? Backups exist but restores were never rehearsed, DNS failover was never tested, and the "warm standby" turns out to be eight months of unapplied schema drift.

## Pattern / Solution
**Define per-tier targets first. Not everything is Tier 0.**

| Tier | Example services | RTO | RPO | Strategy |
|---|---|---|---|---|
| 0 | Auth, payment path | < 15 min | ~0 | Multi-region active-active |
| 1 | Core product APIs | < 1 h | < 1 min | Warm standby + streaming replication |
| 2 | Internal tools | < 8 h | < 24 h | Restore from backup |
| 3 | Batch/analytics | < 3 d | < 24 h | Rebuild from source systems |

**RPO is bought with replication, RTO is bought with automation:**
- RPO near zero → synchronous or async streaming replication to second region (async = replication lag IS your RPO; measure it)
- RTO minutes → infrastructure already exists (IaC applied, DNS health-checked), databases replicating; failover is a routing decision, not a build

**The recovery stack (per tier):**
```hcl
# Tier 1 example: replicated state + pre-built standby
resource "aws_rds_global_cluster" "core" {
  global_cluster_identifier = "core-global"
  engine                    = "aurora-postgresql"
  storage_encrypted         = true
}
# secondary cluster exists BEFORE the disaster, cross-region
```
- Object storage: cross-region replication or provider-native multi-region buckets
- Secrets/config: replicated secret store in the DR region (not a zip in someone's laptop)
- DNS: low-TTL health-checked failover records (see `dns-ttl-strategy.md` — TTL 300 or lower or failover is slower than your RTO)
- Backups: 3-2-1 (3 copies, 2 media, 1 offsite/immutable), with Object Lock/immutability so ransomware cannot delete them

**Rehearse, or it does not exist.** Game-day drill per quarter, minimum:
1. Pick a scenario (region loss is the classic; also test "backup restore only")
2. Execute the actual failover in an isolated environment — restore the latest snapshot, run migration integrity checks, point a staging DNS name at it
3. Measure achieved RTO/RPO against targets. Write both numbers down.
4. Time-box a full region failover once a year if Tier 0/1 exists. Many orgs do it in production with a maintenance window — the only test that counts.

**Drill checklist:**
```bash
# Achieved RPO = replication lag at failure time
psql -c "SELECT now() - pg_last_xact_replay_timestamp() AS lag;"

# Restore smoke test: can apps actually start against restored data?
velero restore create --from-backup nightly-2026-08-12 --wait
kubectl get pods -n app-restore-test   # then hit it with synthetic traffic

# DNS failover actually moves?
dig +short app.example.com @<health-check-aware-resolver>
```

## Gotchas
- Backups are not DR. A backup without a tested restore path, documented credentials, and known recovery time is a hope, not a plan.
- Restores are slow and nobody knows how slow until timed: a 2 TB snapshot restore can take an hour; verify against your RTO arithmetic.
- Schema/config drift between primary and standby silently grows. Automated replication handles data; it does NOT migrate the app version, feature flags, or IaC diffs. Reconcile standby environments with the same deploy pipeline as primary.
- DNS TTL longer than RTO invalidates the plan — clients cache the dead IP. Also caches in front of DNS (OS stub resolvers, browsers) ignore low TTLs.
- Split-brain: failing back after failover is where data loss actually happens. Document the failback procedure (freeze writes, re-seed replication, verify sequence numbers) with the same care as failover.
- Cross-region egress: replication bandwidth and egress fees at restore time are real costs. Replicating everything "just in case" can double the infra bill; tiering keeps it sane.
- Who can declare the disaster? If only the CTO can, and the CTO is asleep in another timezone, your real RTO includes their commute. Pre-delegate declaration authority to on-call.
- Ransomware corrupts replication too: it encrypts data and replication faithfully replicates the encrypted state. Immutable, versioned backups (Object Lock) are the only real defense — test a restore from before the encryption event.

## Related
- `postgresql-backup-restore.md`
- `chaos-engineering-gameday.md`
- `multi-cloud-strategy.md`
- `object-storage-replication.md`
- `dns-ttl-strategy.md`
