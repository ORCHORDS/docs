# blue-green-database-cutover

**Issue:** Switching the production database endpoint from old to new schema version with minimal downtime
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Blue-green for compute is straightforward — swap load balancer targets. For the database layer it is harder because state cannot simply be duplicated and swapped atomically. This entry covers the standard cutover playbook when a breaking schema change is unavoidable.

## Pattern / Solution
**Approach: logical replication + brief write freeze**

1. Provision "green" database (same engine version, new schema applied)
2. Set up logical replication from blue → green; let replication lag reach near-zero
3. Application write freeze (30–60 seconds):
   - Put app in read-only mode via feature flag / maintenance page for write paths
   - Wait for replication lag to hit 0
4. Point connection string / DNS / PgBouncer at green
5. Remove read-only mode; verify smoke tests
6. Keep blue running (read-only) for 30 minutes as fallback
7. Terminate blue replication slot; decommission blue

```
Blue DB ──(logical replication)──▶ Green DB
  ↑                                    │
App ──── write freeze ────────────────▶ App reconnects to Green
```

**AWS RDS blue/green built-in**
```bash
# Create a managed blue/green deployment
aws rds create-blue-green-deployment \
  --blue-green-deployment-name prod-cutover \
  --source arn:aws:rds:us-east-1:123456:db:prod-blue \
  --target-engine-version 15.4 \
  --target-db-parameter-group-name pg15-params

# When ready, switchover (AWS manages the freeze window)
aws rds switchover-blue-green-deployment \
  --blue-green-deployment-identifier bgd-xxxxxxxx
```

## Gotchas
- Logical replication does not replicate DDL — you must apply schema to green manually before streaming data
- Long-running transactions on blue block the replication slot; monitor `pg_replication_slots`
- Sequences on green will lag behind blue; bump them past blue's max before cutover
- Application connection pools hold old connections — force pool drain or restart app after DNS switch
- Always test the cutover in staging with production-sized data first

## Related
- `database-migration-zero-downtime.md`
- `rollback-runbook.md`
- `canary-vs-blue-green-2026.md`
