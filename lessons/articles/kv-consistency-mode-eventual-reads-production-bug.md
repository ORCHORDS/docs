# KV Consistency Mode Default Eventual Reads Production Bug

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Immediately after a user updated their subscription tier, subsequent API calls
returned the old tier for up to 60 seconds. The write had succeeded and KV
showed the correct value from the Cloudflare dashboard. Customers saw "You
don't have access to this feature" errors on features they had just paid to
unlock.

---

## Context

Cloudflare KV is a globally distributed, eventually consistent key-value store.
Writes propagate across Cloudflare's edge network asynchronously. After a
`put()` succeeds, a subsequent `get()` routed to a different edge PoP may
return the previous value until propagation completes. Propagation latency is
typically less than 60 seconds globally but is not bounded.

The Workers SDK `get()` method defaults to **eventual consistency** with no
option to request strongly consistent reads from the same region. There is no
"read-your-writes" guarantee unless the read is routed to the same edge node
that processed the write — and in practice, Worker requests are load-balanced
across many nodes.

The subscription update flow that caused the incident:

```typescript
// BUGGY FLOW
// Step 1: payment webhook worker writes the new tier
await env.KV.put(`subscription:${userId}`, JSON.stringify({ tier: "pro" }), {
  expirationTtl: 86400 * 365,
});

// Step 2: immediately redirect user back to the app
return Response.redirect("https://app.example.com/dashboard", 302);

// Step 3: the app's API worker reads the subscription
//         — may hit a different edge node, returns "free" tier
const raw = await env.KV.get(`subscription:${userId}`);
const subscription = JSON.parse(raw ?? '{"tier":"free"}');
```

---

## Why This Happens

KV replicates writes across hundreds of edge PoPs. The write is acknowledged
once it has been durably stored in a backend cluster, but that acknowledgment
does not mean all PoPs have received the new value. A Worker request served
200ms later in a different PoP reads from its local replica, which may still
hold the previous value.

This is the documented behavior of KV — it is an eventually consistent store
by design. The error was treating it as if it were strongly consistent.

---

## Solutions

### Option 1: Write a "freshness token" and pass it through the redirect

After writing to KV, include a version token in the redirect URL. The
receiving worker uses this token to validate that its read is fresh:

```typescript
// payment webhook worker
const version = crypto.randomUUID();
await env.KV.put(
  `subscription:${userId}`,
  JSON.stringify({ tier: "pro", version }),
  { expirationTtl: 86400 * 365 },
);
// Also store the version separately for cross-check
await env.KV.put(`subscription-version:${userId}`, version, {
  expirationTtl: 300,
});
return Response.redirect(
  `https://app.example.com/dashboard?refresh=${version}`,
  302,
);
```

```typescript
// app API worker — subscription check
async function getSubscription(userId: string, expectedVersion?: string, env: Env) {
  const MAX_WAIT_MS = 5000;
  const POLL_MS = 500;
  const deadline = Date.now() + MAX_WAIT_MS;

  while (Date.now() < deadline) {
    const raw = await env.KV.get(`subscription:${userId}`);
    const sub = JSON.parse(raw ?? '{"tier":"free","version":""}');
    if (!expectedVersion || sub.version === expectedVersion) {
      return sub;
    }
    await new Promise((r) => setTimeout(r, POLL_MS));
  }

  // Timed out — fall back to authoritative source
  return fetchSubscriptionFromDatabase(userId, env);
}
```

### Option 2: Use Durable Objects as the source of truth for subscription state

KV is the wrong primitive for data that must reflect writes immediately.
Durable Objects provide serialized, strongly consistent storage per key:

```typescript
// subscription Durable Object
export class SubscriptionDO implements DurableObject {
  private storage: DurableObjectStorage;

  constructor(state: DurableObjectState) {
    this.storage = state.storage;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "PUT") {
      const body = await request.json<{ tier: string }>();
      await this.storage.put("tier", body.tier);
      return new Response(null, { status: 204 });
    }

    if (request.method === "GET") {
      const tier = (await this.storage.get<string>("tier")) ?? "free";
      return new Response(JSON.stringify({ tier }));
    }

    return new Response("method not allowed", { status: 405 });
  }
}
```

```typescript
// Worker reading subscription
const id = env.SUBSCRIPTION.idFromName(userId);
const stub = env.SUBSCRIPTION.get(id);
const res = await stub.fetch(new Request("https://do/subscription"));
const { tier } = await res.json<{ tier: string }>();
```

Durable Objects guarantee read-your-writes within a single DO instance.
After a write via the DO, any subsequent read from the same DO instance
returns the updated value.

### Option 3: Store subscription state in D1 and use KV only for caching

D1 reads are strongly consistent within a session. Write subscription changes
to D1, use KV only as a short-lived performance cache with a TTL of 30 seconds
or less. On cache miss, always fall through to D1.

```typescript
async function getSubscriptionTier(userId: string, env: Env): Promise<string> {
  // Try KV cache first (short TTL so staleness window is bounded)
  const cached = await env.KV.get(`sub-cache:${userId}`);
  if (cached) return cached;

  // Fall through to D1 — always consistent
  const row = await env.DB.prepare(
    "SELECT tier FROM subscriptions WHERE user_id = ? LIMIT 1"
  )
    .bind(userId)
    .first<{ tier: string }>();

  const tier = row?.tier ?? "free";

  // Populate KV cache for 30s
  await env.KV.put(`sub-cache:${userId}`, tier, { expirationTtl: 30 });
  return tier;
}
```

---

## Anti-patterns

- Using KV for any data that must be consistent immediately after a write
  (authentication tokens, subscription tier, payment status, feature flags
  that gate paywalled content).
- Assuming `put()` success means `get()` will return the new value on the
  next request.
- Setting very long TTLs on KV values that need to be invalidated promptly.
- Relying on KV as the authoritative record for financial or access-control
  decisions without a fallback to a consistent store.

---

## Gotchas

**The `cacheTtl` parameter on `get()` makes things worse**: Passing
`cacheTtl` to `env.KV.get()` instructs the edge to cache the value locally
for that duration. If you write a new value but a nearby PoP has a cached
copy with a long `cacheTtl`, reads from that PoP will return the stale value
for the full TTL duration regardless of the global propagation completing.

**Eventual consistency is not a bug**: KV's design tradeoff is global low-read
latency in exchange for eventual consistency. Understand this at design time,
not at incident time.

**Testing locally hides the issue**: Miniflare and `wrangler dev` use a local
KV store with no propagation delay. Tests always see consistent reads. The
failure mode only surfaces in production against real distributed KV.

**60 seconds is a typical upper bound, not a guarantee**: Cloudflare's docs
say writes propagate "within 60 seconds" under normal conditions. During edge
network incidents propagation can take longer.

---

## Verification

1. After deploying the fix, perform a synthetic transaction: trigger a
   subscription upgrade via the payment webhook, then immediately call the
   subscription API endpoint 10 times in rapid succession. Assert all 10
   responses return the new tier.
2. Instrument the fallback path (D1/DO read after KV miss or stale version)
   with an Analytics Engine data point. Alert if fallback rate exceeds 1% of
   subscription reads — indicates KV propagation is slower than expected.
3. Add a canary test in the CI integration suite that asserts consistency
   behavior is bounded by the chosen architecture (DO / D1 fallback), not
   by KV propagation speed.

---

## Related

- `d1-replica-stale-read-production-incident.md` — stale reads from D1
- `kv-ttl-expiry-race-condition-session-logout-incident.md` — TTL timing bugs
- `kv-read-costs-capacity-planning-retrospective.md` — KV cost model
- `durable-objects-storage-transaction-atomicity-lesson.md` — DO as consistent store

---

## Sources

- Cloudflare KV documentation: "Consistency" section
- Cloudflare Workers documentation: "Durable Objects" — read-your-writes semantics
- Cloudflare community forum: Thread on KV eventual consistency SLA
