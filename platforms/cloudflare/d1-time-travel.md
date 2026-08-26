# d1-time-travel

**Issue:** D1 time travel — restore, debug, audit
**Date:** 2026-08-09
**Status:** documented

## Symptom
You run `DELETE FROM users WHERE 1=1`. The users are
gone. You didn't mean it. You have a backup from
yesterday, but you've lost today's changes.

## Root cause
**Destructive operations are forever.** Use Time Travel.

**Source:** CF D1 Time Travel docs.

## The "Time Travel" pattern

For D1 Time Travel:
- **Restore:** To any point in the last 30 days
- **Bookmarks:** Named restore points
- **Inspect:** Read-only at a point in time

```bash
# Restore to a specific time
npx wrangler d1 time-travel my-db --timestamp="2026-08-09T00:00:00Z"

# Restore to a bookmark
npx wrangler d1 time-travel my-db --bookmark="pre-migration"
```

The DB is restored.

## The "bookmark" pattern

For a bookmark:
```bash
# Create a bookmark
npx wrangler d1 time-travel my-db --bookmark="pre-migration" --create

# Restore to the bookmark
npx wrangler d1 time-travel my-db --bookmark="pre-migration"
```

The bookmark is named.

## The "Time Travel in code" pattern

For programmatic Time Travel (via API):
```ts
// 1. List the restore points
const restorePoints = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${accountId}/d1/database/${databaseId}/time-travel`,
  { headers: { 'Authorization': `Bearer ${token}` } }
).then(r => r.json());

// 2. Restore
await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${accountId}/d1/database/${databaseId}/time-travel/restore`,
  {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ timestamp: '2026-08-09T00:00:00Z' }),
  }
);
```

The Time Travel is programmatic.

## The "Time Travel limits" pattern

For limits:
- **Retention:** 30 days
- **Frequency:** Per request
- **Size:** Per DB

The 30-day retention is enough for most.

## The "Time Travel" use cases

For use cases:
- **Accidental delete:** Restore
- **Bad migration:** Roll back
- **Debug:** Inspect at a point in time
- **Audit:** Replay

The Time Travel is multi-purpose.

## The "Time Travel anti-pattern" anti-patterns

### 1. No bookmark
- **Issue:** Restore is hard
- **Fix:** Bookmark before risky changes

### 2. No backup plan
- **Issue:** Lost data
- **Fix:** Time Travel + R2 backup

### 3. Risky migration
- **Issue:** Can't roll back
- **Fix:** Use expand-contract

### 4. Long retention
- **Issue:** 30 days isn't enough
- **Fix:** Export to R2 for long-term

## Verification
- **Test:** Time Travel works
- **Test:** Bookmark is set
- **Live:** Time Travel is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "no bookmark" anti-pattern.** Bookmark
  before risky changes.
- **The "no backup plan" anti-pattern.** Time Travel
  + R2.
- **The "risky migration" anti-pattern.** Expand-contract.

## Related
- `cloudflare/d1-migration-best-practices.md`
- `cloudflare/d1-batch-bundler-bug.md`
- `feature-cookbook-disaster-recovery.md`
- `zero-downtime-db-migration.md`
- D1 Time Travel: https://developers.cloudflare.com/d1/platform/backup/
