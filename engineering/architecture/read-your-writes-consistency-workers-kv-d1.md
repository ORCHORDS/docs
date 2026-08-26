# Read-Your-Writes Consistency with Workers KV and D1

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A user submits a form, the Worker writes to KV or D1, then immediately redirects to a page that reads the same data—but the page renders the old value. The eventual-consistency window in KV (up to 60 seconds) and cross-region D1 replication lag both cause users to see stale reads immediately after their own writes, eroding trust and producing confusing UX.

## Context

Read-your-writes (RYW) is a session-level consistency guarantee: after a client performs a write, all subsequent reads within that session observe the written value. Cloudflare Workers KV is eventually consistent by design; D1 write replicas propagate asynchronously. Neither platform offers RYW natively, so it must be layered on top using tokens, sticky routing, or short-lived caches. Choosing the right mechanism depends on whether the read and write happen in the same request, same session, or across devices.

## Strategy 1 — Write Token in Cookie

After a successful write, stamp a version token into a cookie. On reads, if the token is present and newer than the cached value's timestamp, bypass KV and read from the authoritative D1 primary (or Durable Object).

```typescript
// src/handlers/profile.ts
import type { Env } from "./env";

const KV_TTL = 60; // seconds

export async function handleUpdateProfile(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<{ name: string; bio: string }>();
  const userId = getUserId(request); // from JWT / session

  // Write to D1 (authoritative)
  await env.DB.prepare(
    "UPDATE users SET name = ?1, bio = ?2, updated_at = unixepoch() WHERE id = ?3"
  )
    .bind(body.name, body.bio, userId)
    .run();

  // Invalidate stale KV entry
  await env.USER_CACHE.delete(`user:${userId}`);

  const writeTs = Date.now();
  const headers = new Headers({ Location: "/profile" });
  // Stamp write token; HttpOnly + SameSite=Strict keeps it session-local
  headers.append(
    "Set-Cookie",
    `ryw_ts=${writeTs}; Path=/; HttpOnly; SameSite=Strict; Max-Age=120`
  );

  return new Response(null, { status: 303, headers });
}

export async function handleGetProfile(
  request: Request,
  env: Env
): Promise<Response> {
  const userId = getUserId(request);
  const cookies = parseCookies(request.headers.get("Cookie") ?? "");
  const rywTs = parseInt(cookies["ryw_ts"] ?? "0", 10);
  const staleCutoff = Date.now() - 5_000; // 5 s grace period

  if (rywTs > staleCutoff) {
    // Recent write in this session → read directly from D1 to guarantee RYW
    const row = await env.DB.prepare("SELECT * FROM users WHERE id = ?1")
      .bind(userId)
      .first();
    return Response.json(row);
  }

  // Normal path: try KV, fall back to D1 on miss
  const cached = await env.USER_CACHE.get(`user:${userId}`, "json");
  if (cached) return Response.json(cached);

  const row = await env.DB.prepare("SELECT * FROM users WHERE id = ?1")
    .bind(userId)
    .first();

  await env.USER_CACHE.put(`user:${userId}`, JSON.stringify(row), {
    expirationTtl: KV_TTL,
  });

  return Response.json(row);
}

function parseCookies(header: string): Record<string, string> {
  return Object.fromEntries(
    header.split(";").map((c) => c.trim().split("=").map(decodeURIComponent) as [string, string])
  );
}

function getUserId(_request: Request): string {
  // extract from JWT / Cloudflare Access header
  return "placeholder";
}
```

## Strategy 2 — Durable Object as Session-Scoped Cache

Route all reads and writes for a user through a Durable Object keyed on `userId`. Because the DO has a single execution context, it trivially achieves RYW without any token juggling.

```typescript
// src/actors/user-session.ts
export class UserSession implements DurableObject {
  private state: DurableObjectState;
  private profile: unknown | null = null;

  constructor(state: DurableObjectState) {
    this.state = state;
    // Restore from hibernation-safe storage
    this.state.blockConcurrencyWhile(async () => {
      this.profile = await this.state.storage.get("profile") ?? null;
    });
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "PUT" && url.pathname === "/profile") {
      const body = await request.json();
      this.profile = body;
      await this.state.storage.put("profile", body);
      return new Response(JSON.stringify({ ok: true }));
    }

    if (request.method === "GET" && url.pathname === "/profile") {
      // Always returns the latest write this session performed — RYW guaranteed
      return Response.json(this.profile ?? {});
    }

    return new Response("Not found", { status: 404 });
  }
}
```

## Strategy 3 — Conditional KV Read with ETag

Embed an ETag in the write response. The client sends `If-None-Match` on the next read; the Worker compares the ETag against a freshly computed one and forces a D1 read when they differ.

```typescript
async function kvsGetWithEtag(
  env: Env,
  key: string,
  clientEtag: string | null
): Promise<{ data: unknown; etag: string }> {
  const { value, metadata } = await env.USER_CACHE.getWithMetadata<{ etag: string }>(key, "json");

  if (value && metadata?.etag && metadata.etag === clientEtag) {
    // Client already has the latest version
    return { data: value, etag: metadata.etag };
  }

  // Cache miss or ETag mismatch → authoritative read
  const row = await env.DB.prepare("SELECT *, updated_at FROM users WHERE id = ?1")
    .bind(key)
    .first<{ updated_at: number }>();

  const newEtag = `"${row?.updated_at ?? Date.now()}"`;
  await env.USER_CACHE.put(key, JSON.stringify(row), {
    expirationTtl: 60,
    metadata: { etag: newEtag },
  });

  return { data: row, etag: newEtag };
}
```

## Anti-patterns

- Relying solely on KV replication to propagate writes—this is eventually consistent and offers no RYW guarantee.
- Using a global Durable Object to proxy all user reads for RYW—this creates a hot partition and removes the benefit of KV's edge distribution.
- Setting an excessively long cookie TTL for the write token—it should expire in 30–120 seconds to avoid bypassing KV indefinitely.

## Gotchas

- D1 read replicas can lag behind the primary by hundreds of milliseconds; when RYW matters, always target the primary with `?_location=primary` or a direct binding read.
- KV `put` followed immediately by `get` in the same Worker invocation may still return the old value because KV is globally distributed; do not rely on same-request reads for RYW.

## Verification

```bash
# 1. Write a profile update
curl -X POST https://your-worker.workers.dev/profile \
  -H "Content-Type: application/json" \
  -c cookies.txt -b cookies.txt \
  -d '{"name":"Alice"}'

# 2. Immediately read back — should return "Alice", not stale value
curl https://your-worker.workers.dev/profile \
  -c cookies.txt -b cookies.txt | jq .name
```

## Related

- `architecture/caching-layers-cloudflare-workers-kv-r2.md`
- `architecture/kv-replication-lag-compensating-patterns.md`
- `architecture/consistency-patterns.md`
- `architecture/cqrs-cloudflare-workers-d1.md`

## Sources

- https://developers.cloudflare.com/kv/reference/consistency/
- https://developers.cloudflare.com/d1/reference/replication/
- https://jepsen.io/consistency/models/read-your-writes
