# Platform-Wide Search Suppression KV Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A post, account, or hashtag needs to be hidden from search results across the entire platform within seconds of a moderation decision — without deleting the content itself. Full deletions trigger appeals; suppression is a softer, reversible tool used during investigations, legal holds, or graduated enforcement.

## Context

example project (example.com) runs search via a Workers AI embedding + D1 FTS hybrid. Suppression must propagate to all 300+ edge PoPs before the next search request lands. KV is the fastest globally-replicated store available in Workers. A suppression entry written to KV with `expirationTtl` becomes the canonical gate; the search Worker checks it on every query before returning results. D1 is the system-of-record for audit and appeal purposes.

---

## KV Suppression Schema

Keys follow `suppress:{type}:{id}` where type is `post`, `account`, or `tag`.

```typescript
// Types
interface SuppressionEntry {
  reason: 'investigation' | 'legal_hold' | 'graduated_enforcement' | 'court_order';
  suppressedAt: number; // epoch ms
  suppressedBy: string; // moderator ID (hashed)
  expiresAt?: number;   // epoch ms, undefined = indefinite
  appealEligible: boolean;
}

async function suppressEntity(
  kv: KVNamespace,
  db: D1Database,
  type: 'post' | 'account' | 'tag',
  id: string,
  entry: SuppressionEntry,
  ttlSeconds?: number,
): Promise<void> {
  const key = `suppress:${type}:${id}`;
  const value = JSON.stringify(entry);

  await kv.put(key, value, ttlSeconds ? { expirationTtl: ttlSeconds } : undefined);

  // D1 audit record — never deleted, only superseded
  await db.prepare(
    `INSERT INTO suppression_log (entity_type, entity_id, reason, suppressed_at, suppressed_by, expires_at, appeal_eligible)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
  ).bind(
    type, id, entry.reason, entry.suppressedAt,
    entry.suppressedBy, entry.expiresAt ?? null, entry.appealEligible ? 1 : 0,
  ).run();
}
```

## Search Gate Middleware

Every search Worker runs the suppression check before returning results. The check is a parallel KV multi-get to avoid serial latency.

```typescript
async function filterSuppressedResults(
  kv: KVNamespace,
  results: Array<{ type: 'post' | 'account' | 'tag'; id: string; [k: string]: unknown }>,
): Promise<typeof results> {
  if (results.length === 0) return [];

  const keys = results.map(r => `suppress:${r.type}:${r.id}`);
  // KV bulk get — up to 100 keys
  const entries = await Promise.all(keys.map(k => kv.get(k)));

  return results.filter((_, i) => entries[i] === null);
}

// Usage inside search handler
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { query } = await req.json<{ query: string }>();
    const rawResults = await runSearch(env.DB, query);
    const visible = await filterSuppressedResults(env.KV, rawResults);
    return Response.json({ results: visible });
  },
};
```

## Bulk Tag Suppression

When a hashtag campaign is suppressed, all posts tagged with it must also be gated. Enumerate via D1, write KV entries in batches.

```typescript
async function suppressTagCascade(
  kv: KVNamespace,
  db: D1Database,
  tag: string,
  moderatorId: string,
  ttlSeconds: number,
): Promise<number> {
  // Suppress the tag itself
  await suppressEntity(kv, db, 'tag', tag, {
    reason: 'graduated_enforcement',
    suppressedAt: Date.now(),
    suppressedBy: moderatorId,
    expiresAt: Date.now() + ttlSeconds * 1000,
    appealEligible: true,
  }, ttlSeconds);

  // Fetch posts — paginate via cursor
  let cursor: string | null = null;
  let count = 0;
  do {
    const rows = await db.prepare(
      `SELECT post_id FROM post_tags WHERE tag = ? AND post_id > ? ORDER BY post_id LIMIT 500`,
    ).bind(tag, cursor ?? '').all<{ post_id: string }>();

    await Promise.all(
      rows.results.map(r =>
        kv.put(`suppress:post:${r.post_id}`, JSON.stringify({
          reason: 'graduated_enforcement',
          suppressedAt: Date.now(),
          suppressedBy: moderatorId,
          expiresAt: Date.now() + ttlSeconds * 1000,
          appealEligible: true,
        }), { expirationTtl: ttlSeconds }),
      ),
    );
    count += rows.results.length;
    cursor = rows.results.at(-1)?.post_id ?? null;
  } while (cursor && rows.results.length === 500);

  return count;
}
```

## Lifting Suppression

Suppression is lifted by deleting the KV key and recording the lift in D1.

```typescript
async function liftSuppression(
  kv: KVNamespace,
  db: D1Database,
  type: 'post' | 'account' | 'tag',
  id: string,
  liftedBy: string,
): Promise<void> {
  await kv.delete(`suppress:${type}:${id}`);
  await db.prepare(
    `INSERT INTO suppression_log (entity_type, entity_id, reason, suppressed_at, suppressed_by, lifted_at, lifted_by)
     VALUES (?, ?, 'lifted', ?, ?, ?, ?)`,
  ).bind(type, id, Date.now(), liftedBy, Date.now(), liftedBy).run();
}
```

## Suppression Dashboard Aggregate

Moderators query D1 for active suppressions (KV TTLs have already pruned expired ones).

```typescript
async function getActiveSuppressions(
  db: D1Database,
  page = 0,
  pageSize = 50,
): Promise<{ rows: unknown[]; total: number }> {
  const [rows, total] = await Promise.all([
    db.prepare(
      `SELECT entity_type, entity_id, reason, suppressed_at, expires_at, appeal_eligible
       FROM suppression_log
       WHERE lifted_at IS NULL AND (expires_at IS NULL OR expires_at > ?)
       ORDER BY suppressed_at DESC LIMIT ? OFFSET ?`,
    ).bind(Date.now(), pageSize, page * pageSize).all(),
    db.prepare(
      `SELECT COUNT(*) as n FROM suppression_log
       WHERE lifted_at IS NULL AND (expires_at IS NULL OR expires_at > ?)`,
    ).bind(Date.now()).first<{ n: number }>(),
  ]);
  return { rows: rows.results, total: total?.n ?? 0 };
}
```

---

## Anti-patterns

- Writing suppression to D1 only and filtering at query time — D1 reads add 5–30 ms; KV reads average <2 ms globally.
- Suppressing by mutating the search index row — makes reversal and audit difficult.
- Using a single KV key for a list of suppressed IDs — KV values max at 25 MB and list scans are O(n).
- Skipping the D1 audit record — legal hold scenarios require an immutable paper trail.

## Gotchas

- KV eventual consistency window is ~60 seconds in the worst case. A suppression decision will propagate within that window but is not instantaneous at all edges.
- KV `expirationTtl` minimum is 60 seconds. Short-window suppressions (< 60 s) must be lifted manually.
- `kv.get()` returns `null` for missing **and** expired keys — treat both as "not suppressed".
- Bulk tag cascade for high-volume tags (>100 k posts) will exceed a single Worker invocation CPU budget. Offload via Queue.

## Verification

```bash
# Check KV suppression key exists
wrangler kv key get "suppress:post:<post_id>" --namespace-id=$KV_ID

# Confirm audit row in D1
wrangler d1 execute example project-db --command \
  "SELECT * FROM suppression_log WHERE entity_id = '<post_id>' ORDER BY suppressed_at DESC LIMIT 5"

# Confirm post absent from search
curl -s -X POST https://example.com/api/search \
  -H "Content-Type: application/json" \
  -d '{"query":"<suppressed keyword>"}' | jq '.results | length'
```

---

## Related

- `platform-audit-log-immutable-d1-workers.md`
- `shadow-banning-reach-limiting-d1-workers.md`
- `content-expiry-auto-deletion-scheduled-d1-workers.md`
- `emergency-content-takedown-circuit-breaker-queues.md`

## Sources

- Cloudflare KV docs — https://developers.cloudflare.com/kv/
- Cloudflare D1 docs — https://developers.cloudflare.com/d1/
- DSA Article 17 (content restriction notification) — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2065
