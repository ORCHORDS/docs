# Hot/Cold Data Tiering — Workers KV, D1, and R2

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A content platform stores millions of documents. A handful are accessed thousands of times per minute ("hot"), most are read a few times per week ("warm"), and the rest sit untouched for months ("cold"). Storing everything in D1 wastes query capacity; storing everything in KV is expensive and loses SQL query power. A tiered architecture maps each tier to the storage primitive that fits its access pattern best.

## Context

Cloudflare provides three complementary storage primitives:

| Tier | Primitive | Characteristics |
|---|---|---|
| Hot | Workers KV | Sub-millisecond global read; eventually consistent; per-key TTL |
| Warm | D1 | SQL queries; consistent reads; millisecond latency; 10 GB per DB |
| Cold | R2 | Object storage; pay-per-request; GB-scale; no egress fees |

The tiering policy decides which tier each object lives in based on a recency/frequency score. Promotion moves data *up* tiers; demotion moves data *down*. Reads always start at the hottest tier and fall through.

---

## Read Path — Waterfall Lookup

```typescript
interface Env {
  HOT_CACHE: KVNamespace;
  DB: D1Database;
  COLD_STORE: R2Bucket;
}

async function getDocument(
  env: Env,
  docId: string,
): Promise<{ body: string; tier: string } | null> {
  // 1. Hot tier — KV
  const hot = await env.HOT_CACHE.get(docId);
  if (hot !== null) return { body: hot, tier: 'hot' };

  // 2. Warm tier — D1
  const row = await env.DB
    .prepare(`SELECT body, access_count FROM documents WHERE id = ?`)
    .bind(docId)
    .first<{ body: string; access_count: number }>();

  if (row) {
    // Promote to hot if access_count crosses threshold
    if (row.access_count >= 50) {
      await env.HOT_CACHE.put(docId, row.body, { expirationTtl: 3600 });
    }
    // Increment counter asynchronously (non-blocking)
    env.DB.prepare(`UPDATE documents SET access_count = access_count + 1 WHERE id = ?`)
      .bind(docId).run(); // fire-and-forget
    return { body: row.body, tier: 'warm' };
  }

  // 3. Cold tier — R2
  const obj = await env.COLD_STORE.get(docId);
  if (obj) {
    const body = await obj.text();
    // Restore to warm tier on first cold read
    await env.DB.prepare(
      `INSERT INTO documents(id, body, access_count) VALUES(?, ?, 1)
       ON CONFLICT(id) DO UPDATE SET access_count = access_count + 1`
    ).bind(docId, body).run();
    return { body, tier: 'cold' };
  }

  return null;
}
```

---

## Write Path — Write Through

```typescript
async function putDocument(env: Env, docId: string, body: string): Promise<void> {
  // Always write to warm tier (D1 is the source of truth)
  await env.DB.prepare(
    `INSERT INTO documents(id, body, access_count)
     VALUES(?, ?, 0)
     ON CONFLICT(id) DO UPDATE SET body = excluded.body`
  ).bind(docId, body).run();

  // Invalidate hot tier so next read repopulates from D1
  await env.HOT_CACHE.delete(docId);
}
```

---

## Demotion — Moving Cold Data to R2

A scheduled Worker (via Cron Trigger) runs nightly to demote infrequently-accessed documents:

```typescript
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const stale = await env.DB
      .prepare(
        `SELECT id, body FROM documents
         WHERE last_accessed_at < unixepoch('now', '-30 days')
         AND access_count < 5
         LIMIT 500`
      )
      .all<{ id: string; body: string }>();

    for (const doc of stale.results) {
      // Archive to R2
      await env.COLD_STORE.put(doc.id, doc.body, {
        httpMetadata: { contentType: 'application/json' },
      });
      // Remove from warm tier
      await env.DB.prepare(`DELETE FROM documents WHERE id = ?`).bind(doc.id).run();
    }
  },
};
```

---

## Access Score Tracking

Replace the simple `access_count` with a time-decayed score for smarter tiering:

```typescript
// Score = access_count / (hours_since_first_access + 1)
// Recomputed on each warm read; stored in documents.score column
async function updateScore(db: D1Database, docId: string): Promise<void> {
  await db.prepare(`
    UPDATE documents
    SET
      access_count = access_count + 1,
      last_accessed_at = unixepoch(),
      score = CAST(access_count + 1 AS REAL)
              / ((unixepoch() - created_at) / 3600.0 + 1)
    WHERE id = ?
  `).bind(docId).run();
}
```

Demotion criterion: `score < 0.1` and `last_accessed_at < 30 days ago`.

---

## Tier Boundaries at a Glance

```
  ┌─────────────────────────────────────────┐
  │  Promote when: access_count ≥ 50        │
  │  Demote when: score < 0.1 AND 30d old   │
  ├────────────┬────────────┬───────────────┤
  │   KV hot   │   D1 warm  │    R2 cold    │
  │  TTL 1 h   │  SQL index │  Glacier-like │
  │  ~0 ms     │  ~5-10 ms  │  ~50-100 ms   │
  └────────────┴────────────┴───────────────┘
```

---

## Anti-patterns

- **Writing everything to KV first** — KV has a 25 MB value limit and no query capability. Using it as the write-through target makes SQL queries impossible and creates stale-data windows on eviction.
- **Promoting eagerly on first access** — a one-hit wonder (e.g., a scraped URL) floods KV with keys that expire unused. Require a minimum access threshold before promotion.
- **Forgetting KV eventual consistency on writes** — after `HOT_CACHE.delete(docId)`, a global KV read in another datacenter may still return the old value for up to 60 s. If strict consistency is needed, skip KV and serve directly from D1.
- **Demoting in the request path** — demotion to R2 involves an R2 write + D1 delete. Never block an HTTP response on this; schedule it as a cron or queue job.

---

## Gotchas

- KV `expirationTtl` minimum is 60 s. Do not attempt to use KV as an in-memory cache with sub-minute TTLs — the put will be rejected.
- R2 `get()` returns `null` on a miss (not an error), consistent with KV. Check explicitly.
- D1 rows count toward the 10 GB per-DB limit. Monitor `SELECT SUM(length(body)) FROM documents` to anticipate tier-pressure.
- A document deleted from D1 but not yet archived to R2 (during a demotion batch) is briefly unreachable — add a `demoting` status flag in D1 to handle the transition window.

---

## Verification

```bash
# Confirm hot-tier hit for a frequently-read document
curl -I https://your-worker.workers.dev/doc/popular-123
# Look for X-Tier: hot header

# Check demotion — document should appear in R2 after cron
wrangler r2 object get YOUR_BUCKET popular-old-doc-id

# Confirm warm tier is free of old documents
wrangler d1 execute YOUR_DB --command \
  "SELECT COUNT(*) FROM documents WHERE last_accessed_at < unixepoch('now','-30 days');"
```

---

## Related

- `caching-layers-cloudflare-workers-kv-r2.md` — layered caching topology
- `cache-aside-pattern.md` — lazy population from the source of truth
- `read-through-cache.md` — transparent cache fill
- `kv-replication-lag-compensating-patterns.md` — handling KV eventual consistency
- `polyglot-persistence-cloudflare-workers.md` — choosing storage primitives

---

## Sources

- Cloudflare KV limits: https://developers.cloudflare.com/kv/platform/limits/
- Cloudflare R2: https://developers.cloudflare.com/r2/
- Cloudflare D1: https://developers.cloudflare.com/d1/
- Jim Gray, "Five-Minute Rule for Trading Memory for Disk Accesses" (1987) — foundational tiering theory
