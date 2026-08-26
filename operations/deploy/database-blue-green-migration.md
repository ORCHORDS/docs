# database-blue-green-migration

**Issue:** DB blue-green — zero-downtime schema changes
**Date:** 2026-08-09
**Status:** documented

## Symptom
You need to change a critical table. The migration
will take 30 min. The table is locked. Users can't
write. The on-call is paged. You wish you had a
zero-downtime migration.

## Root cause
**Schema migrations are risky.** Use blue-green.

**Source:** Liquibase blue-green guide.

## The "blue-green DB" concept

Two parallel databases:
- **Blue:** Current production
- **Green:** New version
- **Sync:** Continuous (logical replication)
- **Switch:** When ready
- **Rollback:** Instant (back to blue)

The migration is zero-downtime.

## The "expand-contract" pattern

For simple migrations, use expand-contract:
1. **Expand:** Add new column (no removal)
2. **Dual-write:** Old + new column
3. **Backfill:** Old data to new
4. **Read new:** App reads new column
5. **Write new only:** Stop writing old
6. **Contract:** Drop old column (later release)

The migration is backwards-compatible.

## The "blue-green phases" pattern

For 6 phases:
```
1. Deploy Green DB
2. Apply schema changes to Green
3. Sync data (logical replication)
4. Verify Green
5. Switch traffic
6. Decommission Blue
```

The phases are sequential.

## The "phase 1: deploy green" pattern

For phase 1:
```yaml
# green-postgres.yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: production-db-green
  labels:
    deployment-color: green
spec:
  instances: 3
  imageName: ghcr.io/cloudnative-pg/postgresql:16.2
  bootstrap:
    recovery:
      source: production-db-blue  # From blue's backup
```

The green is deployed.

## The "phase 2: schema changes" pattern

For phase 2:
```yaml
# migration-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: green-db-migration
  annotations:
    argocd.argoproj.io/hook: PostSync
spec:
  template:
    spec:
      containers:
        - name: migrate
          image: registry.example.com/myapp:v3.0.0
          command:
            - /bin/sh
            - -c
            - |
              export DATABASE_URL=$GREEN_DATABASE_URL
              ./migrate up
              ./migrate version
```

The schema is migrated.

## The "phase 3: replication" pattern

For phase 3 (logical replication):
```sql
-- On blue: create publication
CREATE PUBLICATION blue_to_green FOR ALL TABLES;

-- On green: create subscription
CREATE SUBSCRIPTION green_sub
  CONNECTION 'host=blue-host dbname=mydb user=repl password=...'
  PUBLICATION blue_to_green
  WITH (copy_data = false);
```

The data is replicated.

## The "phase 4: verify" pattern

For phase 4:
```bash
# Compare row counts
BLUE=$(psql -h blue -t -c "SELECT count(*) FROM users")
GREEN=$(psql -h green -t -c "SELECT count(*) FROM users")
if [ "$BLUE" != "$GREEN" ]; then
  echo "MISMATCH"
  exit 1
fi
```

The green is verified.

## The "phase 5: switch" pattern

For phase 5:
```yaml
# Update service
apiVersion: v1
kind: Service
metadata:
  name: database
  labels:
    active-color: green  # Changed from blue
spec:
  externalName: production-db-green-rw
```

The traffic is switched.

## The "phase 6: rollback" pattern

For phase 6 (rollback):
```bash
git revert HEAD
git push
# ArgoCD syncs back to blue
```

The rollback is instant.

## The "phase 7: decommission" pattern

For phase 7:
```sql
-- Drop subscription
DROP SUBSCRIPTION green_sub;
```

The blue is decommissioned after 24-72h.

## The "RDS blue-green" pattern

For AWS RDS (simpler):
- **Built-in:** RDS Blue/Green Deployments
- **Switchover:** < 5 seconds
- **Engine:** Aurora, PostgreSQL, MySQL, MariaDB
- **Use:** Major version upgrades, scaling

The RDS blue-green is built-in.

**Source:** RDS Blue/Green:
https://aws.amazon.com/about-aws/whats-new/2026/01/amazon-rds-blue-green-deployments-reduces-downtime/

## The "5 second" pattern

For RDS single-region:
- **Direct endpoint:** 5 sec downtime
- **Advanced JDBC Driver:** 2 sec
- **No endpoint change:** Required

The switchover is fast.

## The "monitoring" pattern

For monitoring:
- **Both DBs:** During transition
- **Replication lag:** Continuous
- **Error rate:** Both apps
- **Latency:** Both

The migration is monitored.

## The "rollback strategy" pattern

For rollback:
- **Keep blue running:** Until confidence
- **Instant switch:** Back to blue
- **No data loss:** Continuous replication
- **24-72h window:** Before decommission

The rollback is always available.

## The "DB blue-green vs expand-contract" choice

| Use case | Use |
|---|---|
| **Simple schema change** | Expand-contract |
| **Major version upgrade** | Blue-green |
| **Complex migration** | Blue-green |
| **Need to test with prod data** | Blue-green |
| **No downtime requirement** | Either |

For most, **expand-contract** is enough. For major
changes, **blue-green**.

## The "DB blue-green anti-pattern" anti-patterns

### 1. Long migration
- **Issue:** Lock the table
- **Fix:** Online migration

### 2. No rollback
- **Issue:** Stuck with bad migration
- **Fix:** Keep blue running

### 3. No verification
- **Issue:** Data mismatch
- **Fix:** Compare row counts

### 4. No monitoring
- **Issue:** Replication lag
- **Fix:** Monitor

### 5. Decommission too early
- **Issue:** Can't rollback
- **Fix:** Wait 24-72h

## Verification
- **Test:** Schema is migrated
- **Test:** Data is replicated
- **Test:** Switch is fast
- **Test:** Rollback works
- **Live:** Monitored
- **Audit:** Quarterly review

## Gotchas
- **The "no rollback" anti-pattern.** Keep blue.
- **The "decommission too early" anti-pattern.** Wait
  24-72h.
- **The "no verification" anti-pattern.** Compare
  counts.

## Related
- `deploy/canary-deployments.md`
- `deploy/zero-downtime-deploys.md`
- `feature-cookbook-blue-green.md`
- `feature-cookbook-data-modeling.md`
- `cloudflare/d1-time-travel.md`
- Liquibase: https://www.liquibase.com/blog/blue-green-deployments-liquibase
- OneUptime: https://oneuptime.com/blog/post/2026-02-26-argocd-database-blue-green/view
