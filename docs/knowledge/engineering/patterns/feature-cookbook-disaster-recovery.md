# feature-cookbook-disaster-recovery

**Issue:** Disaster recovery — backups, RTO, RPO
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your DB dies. You restore from a backup. The backup is
2 days old. You lost 2 days of data. Your users are
furious.

## Root cause
**Without a DR plan, recovery is slow and lossy.**

**Source:** AWS DR docs:
https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/disaster-recovery-options-in-the-cloud.html

## Key DR metrics

- **RTO (Recovery Time Objective):** How long can the
  system be down? (e.g. 4 hours)
- **RPO (Recovery Point Objective):** How much data loss
  is acceptable? (e.g. 1 hour)
- **MTTR (Mean Time To Recover):** Average time to
  recover. (e.g. 30 min)
- **MTBF (Mean Time Between Failures):** Average time
  between failures. (e.g. 90 days)

Define RTO + RPO before disaster strikes.

## The "backup" pattern

For backups:
- **Full backup:** Snapshot of the entire DB
- **Incremental backup:** Only the changes
- **Differential backup:** All changes since the last
  full backup

For most apps, **daily full + hourly incremental** is a
good balance.

```ts
// Cron: daily backup
async function backup(env: Env, ctx: ExecutionContext): Promise<void> {
  const timestamp = new Date().toISOString().split('T')[0];
  const data = await env.DB!.dump();
  await env.R2!.put(`backups/${timestamp}.db`, data);
}
```

The backup is stored in R2.

## The "D1 point-in-time" pattern

D1 has point-in-time recovery:
- **Time Travel:** Restore to any point in the last 30
  days
- **Backup:** Full DB export

```bash
# Time travel
npx wrangler d1 time-travel my-db --timestamp="2026-08-09T00:00:00Z"
```

D1's Time Travel is built-in.

## The "R2 versioning" pattern

For R2, enable versioning:
```ts
// R2 versioning (CF): enabled per bucket
// Each PUT creates a new version
const old = await env.R2!.get('config.json', { version: '1234' });
```

Versioning allows retrieving old versions.

## The "replica" pattern

For replicas, use a separate region:
- **Primary region:** US East
- **Replica region:** EU West
- **Replication:** Async (eventual consistency)

A replica allows failover.

## The "active-passive failover" pattern

For failover, a standby is ready:
- **Primary:** Active, serves traffic
- **Standby:** Replicated, ready to take over
- **Failover:** Switch DNS to the standby

```ts
async function getDb(env: Env, isFailover: boolean): Promise<D1Database> {
  if (isFailover) return env.DB_SECONDARY!;
  return env.DB_PRIMARY!;
}
```

The failover is a config change.

## The "DNS failover" pattern

For DNS failover:
- **Health check:** CF checks the origin
- **Failover rule:** If origin is down, switch to
  standby
- **TTL:** Short (e.g. 60s) for quick failover

CF has automatic failover.

## The "DR runbook" pattern

For a DR runbook, document every step:
```markdown
# Disaster Recovery Runbook

## Scenario 1: Primary DB down
1. Check the status page: https://status.example.com
2. Verify the DB is down: `curl https://api.example.com/health`
3. If down for > 5 min, initiate failover:
   - `wrangler d1 failover my-db --to-secondary`
4. Verify the failover: `curl https://api.example.com/health`
5. Notify on-call: #incident channel
6. Page the team: PagerDuty

## Scenario 2: D1 Time Travel needed
1. Identify the time: `2026-08-09T00:00:00Z`
2. Restore: `wrangler d1 time-travel my-db --timestamp=...`
3. Verify the data
4. Notify the team

## Scenario 3: R2 bucket corrupted
1. List versions: `r2 object versions --bucket config --key config.json`
2. Restore: `r2 object put --bucket config --key config.json --body old-version.json`
3. Verify
4. Notify
```

The runbook is the manual.

## The "DR drill" pattern

For a DR drill, test the runbook:
1. **Schedule:** Quarterly
2. **Inject failure:** e.g. revoke a permission
3. **Run the runbook:** Follow the steps
4. **Measure RTO:** How long did it take?
5. **Document:** What went well, what didn't
6. **Improve:** Update the runbook

DR is a muscle; you have to exercise it.

## The "3-2-1 backup" rule

For backups, the 3-2-1 rule:
- **3 copies:** Original + 2 backups
- **2 media:** Different storage types (D1 + R2)
- **1 offsite:** In a different region

3-2-1 ensures you can recover.

## The "monitoring" pattern

For monitoring:
- **DB health:** `DB.query({ text: 'SELECT 1' })` every minute
- **Backup success:** Alert if a backup fails
- **RPO violation:** Alert if the last backup is > 1 hour old
- **RTO violation:** Alert if recovery took > 4 hours

The alerts catch the issue.

## The "DR anti-pattern" anti-patterns

### 1. No backups
- **Issue:** When the DB dies, the data is gone
- **Fix:** Backups daily + restore-tested

### 2. No RTO/RPO definition
- **Issue:** You don't know when to declare a disaster
- **Fix:** Define RTO + RPO

### 3. No runbook
- **Issue:** During the incident, you don't know what to
  do
- **Fix:** Document every step

### 4. No drill
- **Issue:** The runbook is wrong; recovery takes 10x
  longer than expected
- **Fix:** Drill quarterly

### 5. Untested backups
- **Issue:** The backup is corrupt; restore fails
- **Fix:** Test restores monthly

### 6. No monitoring
- **Issue:** A failing backup isn't detected
- **Fix:** Alert on backup failure

## Verification
- **Test:** Backup is taken daily
- **Test:** Restore works
- **Test:** RTO is met
- **Test:** RPO is met
- **Live:** Backup health is monitored
- **Audit:** Annual DR review

## Gotchas
- **The "no backups" anti-pattern.** Data is lost on a
  DB crash.
- **The "untested backups" anti-pattern.** The backup
  doesn't restore.
- **The "no RTO/RPO" anti-pattern.** Without a target,
  the recovery takes too long.
- **The "no drill" anti-pattern.** The runbook is wrong.
- **The "single region" anti-pattern.** A region outage
  takes down the app.

## Related
- `safe-deploy-checklist.md`
- `incident-response.md`
- `cloudflare/d1-migration-best-practices.md`
- `scaling-cf-workers.md`
- `feature-resilience-patterns.md`
- `zero-downtime-db-migration.md`
- AWS DR: https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/
