# Workers KV Namespace Key-Limit Exhaustion Postmortem

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Writes to a KV namespace began returning `"KV PUT failed: namespace key limit exceeded"` errors silently
swallowed by a fire-and-forget pattern, causing roughly 6 hours of silent user-preference data loss before
the monitoring alert fired.

## Context
The product stored per-user preferences under a key pattern of `prefs:<userId>` inside a single KV
namespace shared with feature-flag data. After a viral campaign drove sign-ups to 12 million users,
the namespace crossed Cloudflare's documented 10 billion key/namespace ceiling — not because preferences
were that numerous, but because an earlier migration script had written temporary migration state keys and
never cleaned them up, inflating the count by roughly 2 billion phantom entries.

The team had never stress-tested namespace key counts; capacity planning focused entirely on KV read
latency and write throughput, not key cardinality.

## The Silent Failure Pattern

The Worker code responsible for persisting preferences used a fire-and-forget `waitUntil`:

```typescript
// BAD — errors are swallowed
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext) {
    const prefs = await parsePreferences(request);
    ctx.waitUntil(env.PREFS_KV.put(`prefs:${prefs.userId}`, JSON.stringify(prefs)));
    return new Response("ok");
  },
};
```

`KVNamespace.put()` rejects its promise when the namespace is full, but because the rejection was not
awaited or caught inside `waitUntil`, the Worker runtime swallowed it. The HTTP response still returned
`200 ok` to the client. No error surfaced in Workers Logs because unhandled rejections inside
`waitUntil` are not automatically re-thrown to the tail worker.

## Root Cause: Migration Artifacts

The migration script from six months prior wrote temporary staging keys:

```typescript
// Migration script — never cleaned up its temp keys
async function migrateUser(kv: KVNamespace, userId: string, data: LegacyUser) {
  const tempKey = `migration_temp:${userId}:${Date.now()}`;
  await kv.put(tempKey, JSON.stringify(data), { expirationTtl: 86400 });
  // ... migration logic ...
  // BUG: cleanup was in a try block that silently swallowed errors
  try {
    await kv.delete(tempKey);
  } catch (_) {
    // "we can clean this up later" — never did
  }
}
```

The `expirationTtl: 86400` (24 hours) was set but the keys were also explicitly deleted on success, so
the TTL was treated as a safety net. When batch deletes failed during a transient KV hiccup, ~2 billion
temp keys were silently retained. Because key count is not exposed in real-time via the KV API, the
accumulation went undetected.

## Detection and Key Count Audit

Cloudflare's dashboard shows namespace metadata but does not expose live key counts via API. The team
discovered the count only after opening a support ticket. The workaround for key count estimation is to
paginate `list()` with a counter — expensive and slow:

```typescript
async function estimateKeyCount(kv: KVNamespace): Promise<number> {
  let count = 0;
  let cursor: string | undefined;
  do {
    const result = await kv.list({ cursor, limit: 1000 });
    count += result.keys.length;
    cursor = result.list_complete ? undefined : result.cursor;
  } while (cursor);
  return count;
}
```

At scale this is impractical for routine monitoring. The real lesson is to track key insertions and
deletions via Analytics Engine so you maintain a live approximate count yourself.

## Fix: Separate Namespaces + Explicit Error Handling

The immediate fix split the single overloaded namespace into purpose-specific namespaces, and wrapped
all KV writes with explicit error surfacing:

```typescript
// GOOD — errors are captured and reported
async function persistPreferences(
  kv: KVNamespace,
  userId: string,
  prefs: UserPreferences,
  ctx: ExecutionContext
): Promise<void> {
  const writePromise = kv
    .put(`prefs:${userId}`, JSON.stringify(prefs))
    .catch((err: Error) => {
      // Surface to tail worker / Logpush
      console.error(JSON.stringify({
        event: "kv_write_failure",
        namespace: "prefs",
        userId,
        error: err.message,
      }));
      // Re-throw so the caller can decide on fallback
      throw err;
    });
  ctx.waitUntil(writePromise);
}
```

The migration namespace was retired and all temp keys were cleaned up via a scheduled Cron Trigger that
paginated deletes in batches to avoid saturating write throughput.

## Capacity Planning Additions

Going forward, every KV namespace gets a corresponding Analytics Engine write that tracks cumulative
key insertions:

```typescript
async function kvPutWithTracking(
  kv: KVNamespace,
  ae: AnalyticsEngineDataset,
  key: string,
  value: string,
  namespace: string
): Promise<void> {
  await kv.put(key, value);
  ae.writeDataPoint({
    blobs: [namespace],
    doubles: [1],
    indexes: [namespace],
  });
}
```

A companion Cron Trigger queries Analytics Engine daily and pages on-call when estimated key count
exceeds 8 billion (80 % of limit).

## Anti-patterns
- Using a single shared KV namespace for unrelated data domains
- Fire-and-forget `waitUntil` without a `.catch()` handler
- Treating TTL as a substitute for explicit cleanup
- Assuming unhandled rejections inside `waitUntil` will surface as Worker errors

## Gotchas
- KV key count is not exposed via Workers REST API; you must contact support or estimate via list pagination
- `waitUntil` rejection does not propagate to tail workers automatically — you must explicitly catch and log
- KV `list()` pagination at 1 000 keys/page across 10 B keys takes hours; it is not a viable monitoring strategy
- Namespace key limits apply to the total number of distinct keys ever created, including expired-but-not-yet-purged keys during Cloudflare's compaction window

## Verification
1. Write a local Miniflare test that mocks the KV namespace to reject on `put()` and assert the error is
   captured and re-thrown, not swallowed.
2. Deploy a staging namespace with a test Cron Trigger that inserts then verifies deletion of temp keys.
3. Query Analytics Engine with `SELECT SUM(_sample_interval) FROM kv_key_inserts WHERE namespace='prefs'`
   to confirm the counter is accumulating correctly after each write.

## Related
- `kv-write-rate-limit-exceeded-postmortem.md`
- `kv-cold-start-mobile-latency-spike-postmortem.md`
- `kv-read-costs-capacity-planning-retrospective.md`
- `analytics-engine-data-point-limit-exceeded.md`
- `silent-data-loss-partial-writes.md`

## Sources
- Cloudflare KV Limits — https://developers.cloudflare.com/kv/platform/limits/
- Cloudflare Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
- Workers ExecutionContext.waitUntil — https://developers.cloudflare.com/workers/runtime-apis/context/
