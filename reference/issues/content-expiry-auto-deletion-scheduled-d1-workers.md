# Content Expiry and Auto-Deletion via Scheduled D1 Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Anonymous platforms often let users post ephemeral content — confessions, polls, status messages — with a user-chosen TTL (e.g., 1 hour, 24 hours, 7 days). Without automated deletion, expired content lingers in D1 indefinitely, violating user expectations, GDPR Article 5(1)(e) storage-limitation obligations, and growing the database beyond cost-effective bounds. Manual deletion is operationally unsustainable at platform scale.

## Context

Cloudflare Workers Cron Triggers run a scheduled Worker at configurable intervals without an always-on server. D1 supports SQL `DELETE` with `WHERE expires_at < unixepoch()`, making it an ideal match: a cron-fired Worker issues TTL sweeps across content tables, cascades deletions to dependent rows (reactions, reports, media references), and dispatches R2 object deletion for attached media — all within a single scheduled event. D1 batch operations keep round-trips low; pagination via `LIMIT/OFFSET` or a cursor column prevents the Worker from exhausting its 30-second CPU budget on large tables.

## Schema Design with TTL Columns

Every content table carries an `expires_at` integer (UNIX epoch seconds). A `NULL` value means the post does not expire. An index on `expires_at` makes sweeps efficient.

```sql
-- migration: 0010_add_ttl.sql
CREATE TABLE posts (
  post_id     TEXT PRIMARY KEY,
  account_id  TEXT NOT NULL,
  body        TEXT NOT NULL,
  media_key   TEXT,               -- R2 object key, nullable
  created_at  INTEGER NOT NULL,
  expires_at  INTEGER,            -- NULL = never expires
  deleted_at  INTEGER             -- soft-delete tombstone
);

CREATE INDEX idx_posts_expires ON posts(expires_at)
  WHERE expires_at IS NOT NULL AND deleted_at IS NULL;

CREATE TABLE post_reactions (
  reaction_id TEXT PRIMARY KEY,
  post_id     TEXT NOT NULL REFERENCES posts(post_id),
  account_id  TEXT NOT NULL,
  type        TEXT NOT NULL,
  created_at  INTEGER NOT NULL
);

CREATE TABLE post_reports (
  report_id   TEXT PRIMARY KEY,
  post_id     TEXT NOT NULL,
  reason      TEXT NOT NULL,
  created_at  INTEGER NOT NULL
);
```

## TTL Assignment at Post Creation

The Worker handling post creation normalises the caller-supplied TTL against platform limits (minimum 60 s, maximum 30 days) and stores the absolute `expires_at`.

```typescript
// worker: post-create.ts
export interface Env {
  DB: D1Database;
}

const MIN_TTL_SECONDS = 60;
const MAX_TTL_SECONDS = 60 * 60 * 24 * 30; // 30 days

export async function createPost(
  env: Env,
  accountId: string,
  body: string,
  ttlSeconds: number | null,
  mediaKey: string | null = null
): Promise<string> {
  const postId = crypto.randomUUID();
  const now = Math.floor(Date.now() / 1000);

  let expiresAt: number | null = null;
  if (ttlSeconds !== null) {
    const clamped = Math.max(MIN_TTL_SECONDS, Math.min(MAX_TTL_SECONDS, ttlSeconds));
    expiresAt = now + clamped;
  }

  await env.DB.prepare(
    `INSERT INTO posts (post_id, account_id, body, media_key, created_at, expires_at)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6)`
  ).bind(postId, accountId, body, mediaKey, now, expiresAt).run();

  return postId;
}
```

## Scheduled Expiry Sweep Worker

The cron Worker runs every 5 minutes. To stay within the 30-second CPU limit it processes expired posts in pages of 200, soft-deletes them with a tombstone, and collects media keys for R2 cleanup.

```typescript
// worker: expiry-sweep.ts
export interface Env {
  DB: D1Database;
  MEDIA_BUCKET: R2Bucket;
  DELETION_QUEUE: Queue<{ postId: string; mediaKey: string | null }>;
}

const PAGE_SIZE = 200;

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const now = Math.floor(Date.now() / 1000);
    let cursor: string | null = null;
    let totalDeleted = 0;

    // Paginate via post_id cursor to avoid OFFSET performance degradation
    while (true) {
      const cursorClause = cursor ? 'AND post_id > ?3' : '';
      const bindings: (string | number)[] = [now, PAGE_SIZE];
      if (cursor) bindings.push(cursor);

      const { results } = await env.DB.prepare(
        `SELECT post_id, media_key FROM posts
         WHERE expires_at <= ?1
           AND deleted_at IS NULL
           ${cursorClause}
         ORDER BY post_id
         LIMIT ?2`
      ).bind(...bindings).all<{ post_id: string; media_key: string | null }>();

      if (results.length === 0) break;

      // Soft-delete in D1
      const postIds = results.map((r) => r.post_id);
      const placeholders = postIds.map((_, i) => `?${i + 2}`).join(', ');
      await env.DB.prepare(
        `UPDATE posts SET deleted_at = ?1 WHERE post_id IN (${placeholders})`
      ).bind(now, ...postIds).run();

      // Enqueue media keys for R2 deletion (async, non-blocking)
      for (const row of results) {
        if (row.media_key) {
          await env.DELETION_QUEUE.send({ postId: row.post_id, mediaKey: row.media_key });
        }
      }

      totalDeleted += results.length;
      cursor = results[results.length - 1].post_id;

      if (results.length < PAGE_SIZE) break; // last page
    }

    console.log(`[expiry-sweep] soft-deleted ${totalDeleted} posts at epoch ${now}`);
  },
};
```

## Cascading Hard Deletion of Dependent Rows

A second scheduled Worker runs nightly and permanently removes rows that were soft-deleted more than 24 hours ago, along with their dependent reactions and reports. The delay gives moderation Workers time to process any final reports before data disappears.

```typescript
// worker: hard-delete-sweep.ts
export interface Env {
  DB: D1Database;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const cutoff = Math.floor(Date.now() / 1000) - 86_400; // 24 h ago

    // Retrieve IDs to cascade manually (D1 has no ON DELETE CASCADE)
    const { results: stale } = await env.DB.prepare(
      `SELECT post_id FROM posts WHERE deleted_at IS NOT NULL AND deleted_at < ?1 LIMIT 500`
    ).bind(cutoff).all<{ post_id: string }>();

    if (stale.length === 0) return;

    const ids = stale.map((r) => r.post_id);
    const ph = ids.map((_, i) => `?${i + 1}`).join(', ');

    await env.DB.batch([
      env.DB.prepare(`DELETE FROM post_reactions WHERE post_id IN (${ph})`).bind(...ids),
      env.DB.prepare(`DELETE FROM post_reports   WHERE post_id IN (${ph})`).bind(...ids),
      env.DB.prepare(`DELETE FROM posts          WHERE post_id IN (${ph})`).bind(...ids),
    ]);

    console.log(`[hard-delete-sweep] permanently removed ${ids.length} expired posts`);
  },
};
```

## R2 Media Deletion Consumer

A Queue consumer Worker drains the media-deletion queue produced by the soft-delete sweep and calls `R2Bucket.delete()` for each media object.

```typescript
// worker: media-delete-consumer.ts
export interface Env {
  MEDIA_BUCKET: R2Bucket;
}

interface DeletionMessage {
  postId: string;
  mediaKey: string | null;
}

export default {
  async queue(batch: MessageBatch<DeletionMessage>, env: Env): Promise<void> {
    const keys = batch.messages
      .map((m) => m.body.mediaKey)
      .filter((k): k is string => k !== null);

    if (keys.length === 0) {
      batch.ackAll();
      return;
    }

    // R2 deleteMultiple supports up to 1000 keys per call
    await env.MEDIA_BUCKET.delete(keys);
    batch.ackAll();
  },
};
```

## Anti-patterns

- Deleting with `DELETE FROM posts WHERE expires_at < NOW()` in a single unbounded query — on large tables this causes a D1 full-table scan that exceeds the Worker CPU budget and blocks other reads
- Using `OFFSET`-based pagination for the sweep — `OFFSET N` in SQLite re-scans from row 0 each page; use a `post_id > cursor` approach instead
- Hard-deleting dependent rows and the parent row in the same statement via subquery — D1 does not support `DELETE ... WHERE id IN (SELECT ...)` with correlated tables; collect IDs first then batch-delete
- Deleting R2 objects inline in the sweep Worker — R2 `delete()` can be slow for many objects; decouple via Queue to avoid the cron Worker hitting its wall-clock limit
- Setting a minimum TTL of zero — zero-TTL posts expire immediately and congest the sweep queue; enforce a sensible floor (e.g., 60 seconds)

## Gotchas

- `wrangler.toml` cron triggers syntax: `crons = ["*/5 * * * *"]` — the field is an array even for a single trigger
- D1 `IN (...)` with more than ~900 placeholders can exceed the SQLite bind-parameter limit; cap page sizes at 500 or chunk into multiple statements
- Soft-deleted posts should still be returned to moderation tooling (`WHERE deleted_at IS NOT NULL`) but hidden from public feeds (`WHERE deleted_at IS NULL`) — add the `deleted_at IS NULL` predicate to every public-facing query index
- `R2Bucket.delete(keys: string[])` is silent on keys that do not exist — it will not throw for already-deleted objects; this makes the consumer idempotent
- D1's `unixepoch()` and JavaScript `Math.floor(Date.now()/1000)` return the same units (seconds); do not accidentally store milliseconds in `expires_at`

## Verification

1. Create a post with `ttlSeconds = 10` and confirm `expires_at = created_at + 10` in D1.
2. Use `wrangler dev --test-scheduled` to fire the expiry sweep; advance the system clock in the test using a mocked `Date.now` or set `expires_at` to a past value; assert `deleted_at` is populated.
3. Wait 24 h (or manually set `deleted_at` to a past value) and fire the hard-delete sweep; confirm the post row and its reaction/report rows are removed.
4. Confirm the media-deletion queue consumer calls `R2Bucket.delete` with the correct key by intercepting in a vitest integration test with a mocked `R2Bucket`.
5. Run `EXPLAIN QUERY PLAN SELECT ... WHERE expires_at <= ? AND deleted_at IS NULL` in D1 and confirm `idx_posts_expires` is used.

## Related

- `ephemeral-content-secure-deletion-r2.md`
- `right-to-erasure-gdpr-ccpa-deletion-workflow-d1-r2.md`
- `legal-hold-evidence-preservation-d1-r2.md`
- `platform-audit-log-immutable-d1-workers.md`
- `gdpr-data-export-worker-r2-signed-url.md`

## Sources

- GDPR Article 5(1)(e) — storage limitation principle: https://gdpr-info.eu/art-5-gdpr/
- Cloudflare Workers Cron Triggers documentation: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare D1 documentation — batch API and pagination: https://developers.cloudflare.com/d1/
- Cloudflare Queues documentation — consumer Workers: https://developers.cloudflare.com/queues/
- SQLite EXPLAIN QUERY PLAN — index usage verification: https://www.sqlite.org/eqp.html
