# Read-Your-Writes Consistency Pattern — Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A user submits a form, the Worker INSERTs a row into D1, then immediately redirects to a list page. The list page fires a new Worker request that SELECTs from D1 — but the newly inserted row is missing. The user refreshes and the row appears. This is a read-your-writes (RYW) consistency violation: the write happened, but the subsequent read does not reflect it yet.

D1 uses a primary + read-replica topology. Writes always land on the primary; reads may be served by a replica that has not yet replicated the write. Because Cloudflare Workers are stateless and do not hold a persistent DB connection, there is no session-level guarantee that reads after writes see the same connection state.

## Context

- D1 replication lag is typically milliseconds, but under load or during compaction it can extend to seconds.
- The problem surfaces most often in redirect-after-POST patterns, paginated list refreshes, and optimistic UI flows.
- The fix must not require holding a long-lived connection, since Workers have a 30-second CPU limit and are ephemeral.
- Three strategies exist: (1) write a short-lived "pending" token into KV after the mutation, (2) force reads through the primary using `db.withSession()`, or (3) embed the written data client-side to avoid the round-trip entirely.

---

## Strategy 1 — KV Fence Token

After every mutating D1 query, write a fence token into KV with a short TTL. Subsequent reads check for the token; if present, wait briefly or serve the in-memory result directly.

```typescript
// src/lib/ryw-fence.ts
export const RYW_TTL = 5; // seconds

export async function setFence(
  kv: KVNamespace,
  key: string,
  value: string
): Promise<void> {
  await kv.put(`ryw:${key}`, value, { expirationTtl: RYW_TTL });
}

export async function getFence(
  kv: KVNamespace,
  key: string
): Promise<string | null> {
  return kv.get(`ryw:${key}`);
}
```

```typescript
// src/handlers/create-item.ts
export async function handleCreateItem(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<{ name: string; userId: string }>();

  const result = await env.DB.prepare(
    'INSERT INTO items (name, user_id, created_at) VALUES (?, ?, ?) RETURNING id'
  )
    .bind(body.name, body.userId, Date.now())
    .first<{ id: number }>();

  if (!result) throw new Error('Insert failed');

  // Fence: signal that user `userId` has a pending write
  await setFence(env.KV, `user:${body.userId}:items`, String(result.id));

  return Response.json({ id: result.id }, { status: 201 });
}
```

```typescript
// src/handlers/list-items.ts
export async function handleListItems(
  request: Request,
  env: Env
): Promise<Response> {
  const url = new URL(request.url);
  const userId = url.searchParams.get('userId') ?? '';

  const fence = await getFence(env.KV, `user:${userId}:items`);

  // If a fence exists, require the fenced item to appear in results.
  // Retry once after 200ms to allow replication to catch up.
  let rows = await env.DB.prepare(
    'SELECT id, name, created_at FROM items WHERE user_id = ? ORDER BY created_at DESC LIMIT 50'
  )
    .bind(userId)
    .all<{ id: number; name: string; created_at: number }>();

  if (fence && !rows.results.some((r) => String(r.id) === fence)) {
    await scheduler.wait(200);
    rows = await env.DB.prepare(
      'SELECT id, name, created_at FROM items WHERE user_id = ? ORDER BY created_at DESC LIMIT 50'
    )
      .bind(userId)
      .all<{ id: number; name: string; created_at: number }>();
  }

  return Response.json(rows.results);
}
```

---

## Strategy 2 — D1 Session Consistency (`db.withSession`)

D1 supports a session bookmark that pins reads to a minimum replication point. Pass the bookmark from the write response to the subsequent read request via a cookie or response header.

```typescript
// src/handlers/create-with-session.ts
export async function handleCreateWithSession(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<{ name: string; userId: string }>();

  // Open a D1 session so we can capture the write bookmark
  const session = env.DB.withSession('first-unconstrained');

  await session
    .prepare('INSERT INTO items (name, user_id, created_at) VALUES (?, ?, ?)')
    .bind(body.name, body.userId, Date.now())
    .run();

  const bookmark = session.getBookmark();

  return Response.json(
    { ok: true },
    {
      status: 201,
      headers: {
        // Return the bookmark so the client can pass it on the next request
        'X-D1-Bookmark': bookmark ?? '',
      },
    }
  );
}
```

```typescript
// src/handlers/list-with-session.ts
export async function handleListWithSession(
  request: Request,
  env: Env
): Promise<Response> {
  const url = new URL(request.url);
  const userId = url.searchParams.get('userId') ?? '';
  const bookmark = request.headers.get('X-D1-Bookmark') ?? 'first-unconstrained';

  // Pin this read to at least the replication point of the prior write
  const session = env.DB.withSession(bookmark);

  const rows = await session
    .prepare(
      'SELECT id, name, created_at FROM items WHERE user_id = ? ORDER BY created_at DESC LIMIT 50'
    )
    .bind(userId)
    .all<{ id: number; name: string; created_at: number }>();

  return Response.json(rows.results, {
    headers: { 'X-D1-Bookmark': session.getBookmark() ?? '' },
  });
}
```

---

## Strategy 3 — Embed Written Data Client-Side

When the write response already contains the full created object, the client can prepend it to its local list without refetching. No server-side coordination needed.

```typescript
// Client-side (TypeScript / React)
async function createItem(name: string, userId: string) {
  const res = await fetch('/api/items', {
    method: 'POST',
    body: JSON.stringify({ name, userId }),
  });
  const created = await res.json(); // { id, name, created_at }

  // Optimistically update local state — no GET needed
  setItems((prev) => [created, ...prev]);
}
```

---

## Choosing Between Strategies

| Strategy | Latency cost | Complexity | Best for |
|---|---|---|---|
| KV Fence Token | +200ms on miss | Medium | Simple list/detail flows |
| D1 Session Bookmark | ~0ms | Low (needs client cooperation) | Multi-step forms, APIs with smart clients |
| Client-side embed | 0ms | Lowest | SPAs, mobile apps |

---

## Anti-patterns

- **Sleeping unconditionally**: `await scheduler.wait(500)` on every list request punishes all users to fix an edge case.
- **Using KV as the authoritative store**: KV is eventually consistent too; it is only used here as a fast, short-lived signal, not as the data store.
- **Long TTLs on fence tokens**: A 60-second TTL causes unnecessary retries long after replication has caught up. Keep it at 5–10 seconds.
- **Ignoring the bookmark on redirects**: Generating the session bookmark on the write side but not forwarding it to the read side defeats the purpose entirely.

## Gotchas

- `db.withSession()` requires a D1 binding that supports sessions; verify with `wrangler d1 info <database-name>`.
- `scheduler.wait()` counts against the Worker's CPU time budget; use it sparingly.
- The KV fence approach adds one extra KV read per list request. Cache the fence check in a `Map` for the lifetime of a single Worker invocation if the list handler calls it in a loop.
- D1 bookmarks are opaque strings; do not parse or compare them — treat them as tokens.

## Verification

```bash
# Confirm session bookmark header is present after a POST
curl -si -X POST https://api.example.com/items \
  -H 'Content-Type: application/json' \
  -d '{"name":"test","userId":"u1"}' | grep X-D1-Bookmark

# Confirm the bookmark is honoured on the GET
curl -s https://api.example.com/items?userId=u1 \
  -H 'X-D1-Bookmark: <value from above>' | jq '.[0].name'
# Should print "test" immediately, not require a refresh
```

## Related

- `cache-aside-kv-d1-fallback.md`
- `write-through-cache-workers-kv-d1.md`
- `snapshot-isolation-d1-optimistic-concurrency.md`
- `idempotency-key-pattern-workers-d1.md`

## Sources

- Cloudflare D1 docs — Session consistency and bookmarks: https://developers.cloudflare.com/d1/worker-api/d1-database/#withsession
- Cloudflare Workers docs — `scheduler.wait`: https://developers.cloudflare.com/workers/runtime-apis/scheduler/
- "Consistency models" — Peter Bailis et al., VLDB 2014
