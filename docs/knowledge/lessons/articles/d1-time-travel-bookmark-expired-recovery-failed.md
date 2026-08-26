# D1 Time Travel Bookmark Expiry: Recovery Window Missed

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A bulk-delete script with an off-by-one error destroyed 94,000 user-preference rows in
production. We attempted to use D1 Time Travel to restore from a bookmark taken 30 minutes
before the incident. The `wrangler d1 time-travel restore` command returned:

```
Error: Bookmark d1-bookmark-01HZQVF3... is no longer valid.
The requested point in time has exceeded the maximum retention window (30 days).
```

The bookmark was 31 days old — the team had snapshotted it during a scheduled DR drill
the previous month and never refreshed it. No newer bookmark existed. Recovery required
reconstructing the deleted rows from application-level event logs over 18 hours.

## Context

D1 Time Travel allows point-in-time restore within a **30-day rolling window**. Bookmarks
are opaque tokens that reference a specific WAL position. Once the underlying WAL page
is older than 30 days, the bookmark is invalid even if the token was stored correctly.
Bookmarks do not extend the retention window — they only provide a named pointer into it.

Our DR procedure created a bookmark at each monthly drill but never tested restore against
production data volume, and never refreshed the bookmark after each drill.

---

## Timeline

| UTC | Event |
|-----|-------|
| 03:12 | Automated maintenance script runs bulk-delete with incorrect `WHERE` clause predicate |
| 03:14 | Monitoring detects user-preference cache miss spike; no alert fired (below threshold) |
| 06:45 | Customer support reports mass preference-reset complaints |
| 07:03 | Engineering confirms bulk-delete destroyed 94,000 rows |
| 07:09 | Team attempts Time Travel restore from 30-day-old DR bookmark |
| 07:11 | Restore fails: bookmark expired |
| 07:25 | Decision: reconstruct from event log in application database |
| 25:30 | Reconstruction complete (18 h total) |

---

## D1 Time Travel Retention Window — How It Actually Works

D1 Time Travel is built on Cloudflare's WAL-based replication. Cloudflare retains WAL
segments for 30 days from the moment they are written. A bookmark captures a WAL sequence
number (LSN). When all WAL segments at or before that LSN age out, the bookmark becomes
unrestorable regardless of when the bookmark token was created.

```bash
# Create a bookmark — captures current WAL position
wrangler d1 time-travel info --bookmark=now DATABASE_NAME
# Output: d1-bookmark-01HZQVF3XXXXXXXXXXXXXXXXXX

# Restore to a bookmark (must be < 30 days old)
wrangler d1 time-travel restore \
  --bookmark=d1-bookmark-01HZQVF3XXXXXXXXXXXXXXXXXX \
  DATABASE_NAME
```

A bookmark created 30 days ago points to WAL data that no longer exists. The token itself
is permanent but it cannot resolve to actual data.

---

## Fix: Automated Bookmark Refresh and Retention Ladder

The fix has two components: a short-interval bookmark refresh and a retention ladder that
ensures at least one restorable bookmark always exists within the 30-day window.

```typescript
// bookmark-refresh.ts — runs as a Cloudflare Workers Cron Trigger every 24 hours
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const db = env.DB; // D1 binding

    // Insert a sentinel row to force a WAL write, then read back the
    // Time Travel info via the REST API to capture the new bookmark.
    await db.prepare(
      "INSERT OR REPLACE INTO _tt_heartbeat (id, ts) VALUES (1, ?)"
    ).bind(Date.now()).run();

    const accountId = env.CF_ACCOUNT_ID;
    const dbId      = env.D1_DATABASE_ID;
    const apiToken  = env.CF_API_TOKEN;

    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${accountId}/d1/database/${dbId}/time_travel/info`,
      { headers: { Authorization: `Bearer ${apiToken}` } }
    );
    const { result } = await res.json<{ result: { bookmark: string } }>();

    // Store bookmark in KV with TTL ladder: keep last 7, 14, and 28-day bookmarks
    const day = new Date().toISOString().slice(0, 10);
    await env.KV.put(`d1-bookmark:daily:${day}`, result.bookmark, {
      expirationTtl: 60 * 60 * 24 * 28, // 28 days — inside the 30-day window
    });

    console.log(`D1 bookmark refreshed: ${result.bookmark} for ${day}`);
  },
};
```

```toml
# wrangler.toml — cron trigger for bookmark refresh
[[triggers.crons]]
crons = ["0 2 * * *"]  # 02:00 UTC daily
```

---

## Restore Runbook (Updated)

```bash
# 1. List available daily bookmarks from KV
wrangler kv key list --namespace-id=<KV_NS_ID> --prefix="d1-bookmark:daily:"

# 2. Fetch the bookmark value for the target date (e.g. 2026-07-24)
wrangler kv key get --namespace-id=<KV_NS_ID> "d1-bookmark:daily:2026-07-24"

# 3. Restore (bookmark must be < 30 days old — verify before invoking)
wrangler d1 time-travel restore \
  --bookmark=<VALUE_FROM_STEP_2> \
  --timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ -d "2 hours ago") \
  DATABASE_NAME

# 4. Validate row count and data integrity before promoting
wrangler d1 execute DATABASE_NAME \
  --command="SELECT COUNT(*) FROM user_preferences"
```

---

## Anti-patterns

- Treating a Time Travel bookmark as a permanent snapshot. Bookmarks expire with the WAL
  data they reference — they are pointers, not copies.
- Performing DR drills against production bookmarks taken weeks earlier without verifying
  restorability at drill time.
- Relying solely on Time Travel for recovery without a complementary export-to-R2 strategy.
- Not testing restore against realistic data volumes; small DR databases restore in
  seconds but large databases may exceed restore timeout limits.

---

## Gotchas

- The 30-day window is measured from **WAL write time**, not from **bookmark creation time**.
  A bookmark created today pointing to WAL data from yesterday is already 1 day into its
  30-day life.
- D1 Time Travel restores are **destructive** — the database is reverted to the bookmark
  state and all writes after that point are lost. Always clone to a throwaway database
  first: `wrangler d1 time-travel restore --destination-db=<TEMP_DB_NAME> ...`
- Time Travel is not available on D1 databases in the `alpha` tier; it requires at least
  the `workers_paid` plan.
- Restoring a database that a Durable Object depends on may leave the DO's in-memory
  state diverged from the restored D1 state. Drain all DO instances before restoring.

---

## Verification

Post-fix checklist (run monthly):

1. `wrangler kv key list --prefix="d1-bookmark:daily:"` — confirm 28 daily bookmarks exist.
2. Pick the oldest bookmark and run a restore against a throwaway `--destination-db`; confirm
   it completes without error.
3. Verify row count of restored throwaway DB matches expected baseline.
4. Delete the throwaway DB: `wrangler d1 delete <TEMP_DB_NAME>`.
5. Confirm cron trigger shows last successful run in Workers Analytics < 25 hours ago.

---

## Related

- `d1-migration-rollback-failed-production-lesson.md`
- `d1-replica-stale-read-production-incident.md`
- `d1-write-contention-viral-event-postmortem.md`
- `test-your-backups-not-just-your-backup-process.md`
- `never-delete-without-soft-delete-first.md`

---

## Sources

- Cloudflare Docs — D1 Time Travel: https://developers.cloudflare.com/d1/reference/time-travel/
- Cloudflare Docs — D1 REST API: https://developers.cloudflare.com/api/operations/cloudflare-d1-list-databases
- Internal incident ticket INC-2026-0287
- Internal DR drill log DR-2026-Q1
