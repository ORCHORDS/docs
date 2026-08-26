# Workers KV Atomic-Operation Race Conditions and Double-Spend Prevention

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker uses KV as the backing store for a counter, a balance, a one-time-use
token, or a rate-limit window. Under concurrent requests — common at Cloudflare's edge where
thousands of PoPs may serve the same KV namespace — the classic read-modify-write pattern
races: two Workers can both read the same value, both compute an updated value, and both write
back, causing one update to be silently lost.

Symptoms in production:

- Credits debited twice without balance reaching zero
- A one-time coupon redeemed multiple times within the same millisecond window
- Rate-limit counters that allow more requests than the configured ceiling
- Idempotency keys that do not prevent duplicate processing under replay

Workers KV does **not** support compare-and-swap (CAS), atomic increment, or transactions.
This article covers the patterns that compensate for this limitation.

---

## Context

Workers KV is an eventually-consistent, last-write-wins store. Two concurrent `put()` calls to
the same key will both succeed; the one that arrives at the coordination layer last wins.
Strong consistency is not guaranteed even within a single PoP during a burst.

For workloads that require strong atomicity, the correct primitive is:

| Requirement | Recommended primitive |
|---|---|
| Atomic counter / rate limit | Durable Objects (in-memory, single actor) |
| Idempotency / deduplication | D1 with `INSERT OR IGNORE` + unique constraint |
| Balance / inventory | Durable Objects or D1 with explicit transaction |
| Feature flags / config (eventually consistent ok) | KV — safe for read-heavy, write-rare data |

This article shows how to implement each pattern and how to guard KV-backed operations when
migrating to a safer primitive is not yet feasible.

---

## Code sections

### 1. Vulnerable KV counter — the double-spend pattern

```typescript
// VULNERABLE — do not use for anything requiring exactness
export async function decrementBalance_UNSAFE(
  kv: KVNamespace,
  userId: string,
  amount: number
): Promise<boolean> {
  const raw = await kv.get(`balance:${userId}`);
  const balance = parseInt(raw ?? "0", 10);

  if (balance < amount) return false; // insufficient funds

  // RACE: another request reads the same balance here
  await kv.put(`balance:${userId}`, String(balance - amount));
  // RACE: both requests write back balance - amount, duplicating the debit
  return true;
}
```

### 2. Durable Object atomic counter — the correct replacement

```typescript
// durable-objects/balance.ts
export class Balance implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const body = await request.json<{ amount?: number }>();

    if (request.method === "POST" && url.pathname === "/debit") {
      const amount = body.amount ?? 0;

      // blockConcurrencyWhile serialises all access to this DO instance
      return this.state.blockConcurrencyWhile(async () => {
        const balance = (await this.state.storage.get<number>("balance")) ?? 0;

        if (balance < amount) {
          return new Response(JSON.stringify({ ok: false, reason: "insufficient" }), {
            status: 422,
            headers: { "Content-Type": "application/json" },
          });
        }

        await this.state.storage.put("balance", balance - amount);

        return new Response(JSON.stringify({ ok: true, balance: balance - amount }), {
          headers: { "Content-Type": "application/json" },
        });
      });
    }

    if (request.method === "GET" && url.pathname === "/balance") {
      const balance = (await this.state.storage.get<number>("balance")) ?? 0;
      return new Response(JSON.stringify({ balance }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response("Not Found", { status: 404 });
  }
}
```

Worker routing to the Durable Object per user:

```typescript
// worker.ts
export interface Env {
  BALANCE: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const userId = request.headers.get("X-User-Id");
    if (!userId) return new Response("Missing user ID", { status: 400 });

    // Deterministic routing: one DO instance per user
    const id = env.BALANCE.idFromName(`user:${userId}`);
    const stub = env.BALANCE.get(id);
    return stub.fetch(request);
  },
};
```

### 3. D1 idempotency key — prevent duplicate processing

```typescript
// Idempotency keys stored in D1 with a unique constraint
// One-time deduplication window with TTL-based cleanup

const IDEMPOTENCY_TTL_SECONDS = 86_400; // 24 hours

export async function withIdempotency<T>(
  db: D1Database,
  idempotencyKey: string,
  operation: () => Promise<T>
): Promise<{ result: T; duplicate: boolean }> {
  // Attempt to insert; if key already exists, this is a duplicate
  const insert = await db
    .prepare(
      `INSERT OR IGNORE INTO idempotency_keys (ikey, created_at)
       VALUES (?, unixepoch())`
    )
    .bind(idempotencyKey)
    .run();

  if (insert.meta?.rows_written === 0) {
    // Key was already present — retrieve cached result
    const cached = await db
      .prepare(`SELECT result_json FROM idempotency_keys WHERE ikey = ?`)
      .bind(idempotencyKey)
      .first<{ result_json: string }>();

    return {
      result: JSON.parse(cached?.result_json ?? "null"),
      duplicate: true,
    };
  }

  // Key is new — run the operation and persist the result
  const result = await operation();
  await db
    .prepare(
      `UPDATE idempotency_keys SET result_json = ? WHERE ikey = ?`
    )
    .bind(JSON.stringify(result), idempotencyKey)
    .run();

  return { result, duplicate: false };
}
```

D1 schema with TTL cleanup:

```sql
CREATE TABLE IF NOT EXISTS idempotency_keys (
  ikey        TEXT    PRIMARY KEY,
  result_json TEXT,
  created_at  INTEGER NOT NULL
);

-- Cron trigger runs: DELETE FROM idempotency_keys WHERE created_at < unixepoch() - 86400
```

### 4. KV-backed one-time token with optimistic concurrency via metadata version

When migrating to Durable Objects is not yet feasible, a weaker mitigation is to use KV
`getWithMetadata` to read the stored version, then `put` only if the expected version matches.
This does not provide true CAS, but the `expirationTtl` option combined with a single-write
design eliminates the reuse window for short-lived tokens.

```typescript
// One-time token: valid only for first consumer, enforced via D1 unique constraint
export async function consumeOneTimeToken(
  kv: KVNamespace,
  db: D1Database,
  token: string
): Promise<boolean> {
  // First check: KV existence (fast, eventually consistent)
  const value = await kv.get(`ott:${token}`);
  if (!value) return false; // token already consumed or never issued

  // Second check: D1 unique constraint prevents double-spend (strongly consistent)
  const result = await db
    .prepare(
      `INSERT OR IGNORE INTO consumed_tokens (token, consumed_at)
       VALUES (?, unixepoch())`
    )
    .bind(token)
    .run();

  if ((result.meta?.rows_written ?? 0) === 0) {
    return false; // D1 race won by another request
  }

  // Mark consumed in KV immediately (TTL of 0 for immediate deletion)
  await kv.delete(`ott:${token}`);
  return true;
}

export async function issueOneTimeToken(
  kv: KVNamespace,
  payload: string,
  ttlSeconds = 900
): Promise<string> {
  const token = crypto.randomUUID();
  await kv.put(`ott:${token}`, payload, { expirationTtl: ttlSeconds });
  return token;
}
```

### 5. Sliding-window rate limit via Durable Objects (atomic, no race)

```typescript
// durable-objects/rate-limiter.ts
const WINDOW_MS = 60_000; // 1 minute
const MAX_REQUESTS = 100;

export class RateLimiter implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    return this.state.blockConcurrencyWhile(async () => {
      const now = Date.now();
      const stored = (await this.state.storage.get<number[]>("hits")) ?? [];

      // Evict timestamps outside the window
      const window = stored.filter((t) => now - t < WINDOW_MS);

      if (window.length >= MAX_REQUESTS) {
        const retryAfter = Math.ceil((window[0] + WINDOW_MS - now) / 1000);
        return new Response("Rate limit exceeded", {
          status: 429,
          headers: {
            "Retry-After": String(retryAfter),
            "X-RateLimit-Limit": String(MAX_REQUESTS),
            "X-RateLimit-Remaining": "0",
          },
        });
      }

      window.push(now);
      await this.state.storage.put("hits", window);

      return new Response("OK", {
        headers: {
          "X-RateLimit-Limit": String(MAX_REQUESTS),
          "X-RateLimit-Remaining": String(MAX_REQUESTS - window.length),
        },
      });
    });
  }
}
```

### 6. Test: asserting no double-spend under concurrent load (Vitest)

```typescript
// test/double-spend.test.ts
import { describe, it, expect } from "vitest";
import { createExecutionContext, waitOnExecutionContext } from "cloudflare:test";

describe("Balance Durable Object — no double-spend", () => {
  it("concurrent debits do not overdraw balance", async () => {
    // Setup: initialise balance of 10 units
    // Fire 20 concurrent debit requests of 1 unit each
    const INITIAL = 10;
    const CONCURRENCY = 20;
    const DEBIT = 1;

    // Worker test harness (MINIFLARE / Vitest Cloudflare)
    const responses = await Promise.all(
      Array.from({ length: CONCURRENCY }, () =>
        fetch("http://localhost/debit", {
          method: "POST",
          body: JSON.stringify({ amount: DEBIT }),
          headers: { "Content-Type": "application/json", "X-User-Id": "u1" },
        })
      )
    );

    const successes = responses.filter((r) => r.status === 200).length;
    const failures = responses.filter((r) => r.status === 422).length;

    // Exactly INITIAL debits should succeed; the rest should fail
    expect(successes).toBe(INITIAL);
    expect(failures).toBe(CONCURRENCY - INITIAL);
    expect(successes + failures).toBe(CONCURRENCY);
  });
});
```

---

## Anti-patterns

- Using `kv.get()` + `kv.put()` for any value that must be consistent under concurrency — there is no CAS primitive in KV.
- Assuming that setting a short `expirationTtl` on a KV key prevents concurrent reads from both seeing the key before it expires.
- Using KV list operations to count active sessions or tokens — `kv.list()` is eventually consistent and may miss recently written keys.
- Storing account balances or inventory counts in KV and reconciling them with a background cron — the reconcile window is the attack surface.
- Checking an idempotency key in KV and then writing the result in KV without an atomic check-and-set — two identical concurrent requests both miss the key and both execute the operation.

---

## Gotchas

- Durable Objects serialise access via `blockConcurrencyWhile`, but only within a single DO instance. The instance is determined by the stub ID. Two different stubs for the same logical entity would race just like KV. Always derive the DO ID from the entity key (`idFromName`).
- `DurableObjectState.storage.put()` inside `blockConcurrencyWhile` is transactional with the concurrency lock; calling `put()` outside the block is not serialised.
- Workers KV's `put` operation may take up to 60 seconds to propagate globally. A token written in one PoP and consumed 1 ms later in another PoP may not yet be visible. One-time tokens must use a strongly consistent backing store (D1 or DO) for the enforcement step.
- Durable Objects have a single-location constraint for storage access. For global low-latency, use DO for atomicity but cache read results in KV with a short TTL.
- The D1 `INSERT OR IGNORE` pattern relies on a `PRIMARY KEY` or `UNIQUE` constraint on the idempotency key column. Verify the constraint exists; without it, `INSERT OR IGNORE` silently inserts duplicates.

---

## Verification

```bash
# 1. Run the double-spend test with wrangler/vitest integration
npx vitest run test/double-spend.test.ts

# 2. Stress-test with 50 concurrent curl calls and count successes
for i in $(seq 1 50); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST https://worker.example.com/debit \
    -H "Content-Type: application/json" \
    -H "X-User-Id: u-stress-test" \
    -d '{"amount":1}' &
done | wait && echo "Done"
# Tally: count of 200 should equal initial balance; count of 422 = remainder

# 3. Verify idempotency key table state
wrangler d1 execute orchords-db \
  --command "SELECT count(*) FROM idempotency_keys WHERE created_at > unixepoch() - 3600"

# 4. Check DO alarm is not firing false alerts (via tail workers)
wrangler tail --format pretty | grep -i "rate limit"
```

---

## Related

- `rate-limiting-sliding-window-durable-objects.md`
- `durable-objects-auth-patterns.md`
- `api-replay-prevention-nonce-d1-workers.md`
- `d1-atomic-transactions-toctou-prevention.md`
- `token-bucket-rate-limiting-durable-objects.md`
- `idempotency-one-time-secret-replay.md`

---

## Sources

- Cloudflare Workers KV consistency model — https://developers.cloudflare.com/kv/reference/how-kv-works/
- Cloudflare Durable Objects documentation — https://developers.cloudflare.com/durable-objects/
- Martin Fowler: "Optimistic Offline Lock" pattern — https://martinfowler.com/eaaCatalog/optimisticOfflineLock.html
- CWE-362: Race Condition / TOCTOU — https://cwe.mitre.org/data/definitions/362.html
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
