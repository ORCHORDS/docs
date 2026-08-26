# circuit-breaker-workers-d1-fetch

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

A Cloudflare Worker calls an external API (payment processor, email
provider, geocoding service) or runs a D1 query. The downstream
begins returning 503s. Every incoming mobile request now waits out
the full timeout before receiving an error. Latency climbs from 80ms
to 8s. Retry-on-error logic in the mobile app multiplies the load.
The downstream collapses under retry storms.

## Context

Cloudflare Workers run in V8 isolates with a 30-second wall-clock
limit per request. An in-memory circuit breaker resets on every
cold start — useless at any real scale. KV provides edge-persistent
state with ~1ms read latency and ~10ms write latency, making it the
right home for circuit-breaker state in a Workers deployment.

The three-state machine (closed → open → half-open) must be stored
outside the isolate, and the half-open probe must be serialised so
only one request probes — not every concurrent request that arrives
during cooldown.

```
CLOSED ──(failures ≥ threshold)──► OPEN
  ▲                                   │
  │                              (cooldown expires)
  │                                   ▼
  └────(probe succeeds)────── HALF-OPEN
         (probe fails) ──────────────► OPEN
```

## KV State Schema

Each protected resource gets one KV key. The value is a small JSON
object written atomically on every state transition.

```ts
interface BreakerState {
  state: 'closed' | 'open' | 'half-open';
  failures: number;
  lastFailureAt: number;   // epoch ms
  openedAt: number | null; // epoch ms, null when closed
  probeAt: number | null;  // epoch ms, null unless half-open probe in flight
}

const DEFAULT: BreakerState = {
  state: 'closed',
  failures: 0,
  lastFailureAt: 0,
  openedAt: null,
  probeAt: null,
};
```

KV key pattern: `cb:<resource-id>` — e.g. `cb:stripe-charges`,
`cb:d1-primary`, `cb:geocode-api`.

## Core Implementation

```ts
const THRESHOLD  = 5;          // consecutive failures to open
const COOLDOWN   = 30_000;     // ms before half-open probe
const PROBE_LOCK = 5_000;      // ms probe lock (prevents thundering-herd on half-open)

async function readBreaker(env: Env, key: string): Promise<BreakerState> {
  const raw = await env.BREAKERS.get(key);
  return raw ? (JSON.parse(raw) as BreakerState) : { ...DEFAULT };
}

async function writeBreaker(env: Env, key: string, s: BreakerState): Promise<void> {
  await env.BREAKERS.put(key, JSON.stringify(s), { expirationTtl: 300 }); // auto-expire stale open
}

export async function withBreaker<T>(
  env: Env,
  resource: string,
  fn: () => Promise<T>,
): Promise<T> {
  const key = `cb:${resource}`;
  const breaker = await readBreaker(env, key);
  const now = Date.now();

  if (breaker.state === 'open') {
    const elapsed = now - (breaker.openedAt ?? now);
    if (elapsed < COOLDOWN) {
      throw new BreakerOpenError(resource, COOLDOWN - elapsed);
    }
    // Transition to half-open — only if no probe already in flight
    if (breaker.probeAt && now - breaker.probeAt < PROBE_LOCK) {
      throw new BreakerOpenError(resource, PROBE_LOCK - (now - breaker.probeAt));
    }
    breaker.state = 'half-open';
    breaker.probeAt = now;
    await writeBreaker(env, key, breaker);
  }

  try {
    const result = await fn();
    // Success
    if (breaker.state === 'half-open' || breaker.failures > 0) {
      await writeBreaker(env, key, { ...DEFAULT });
    }
    return result;
  } catch (err) {
    const updated: BreakerState = {
      ...breaker,
      failures: breaker.failures + 1,
      lastFailureAt: now,
      state: breaker.failures + 1 >= THRESHOLD ? 'open' : 'closed',
      openedAt: breaker.failures + 1 >= THRESHOLD ? now : null,
      probeAt: null,
    };
    await writeBreaker(env, key, updated);
    throw err;
  }
}

class BreakerOpenError extends Error {
  constructor(resource: string, retryAfterMs: number) {
    super(`Circuit open for ${resource}; retry after ${Math.ceil(retryAfterMs / 1000)}s`);
    this.name = 'BreakerOpenError';
    this.retryAfterMs = retryAfterMs;
  }
  retryAfterMs: number;
}
```

## Protecting D1 and Fetch Calls

Wrap every distinct failure domain in its own breaker — D1
and external fetches fail independently.

```ts
// D1 read protected by a breaker
async function getUser(env: Env, userId: string): Promise<User | null> {
  return withBreaker(env, 'd1-primary', () =>
    env.DB.prepare('SELECT * FROM users WHERE id = ?').bind(userId).first<User>()
  );
}

// External fetch protected by its own breaker
async function chargeCard(env: Env, payload: ChargePayload): Promise<ChargeResult> {
  return withBreaker(env, 'stripe-charges', async () => {
    const res = await fetch('https://api.stripe.com/v1/charges', {
      method: 'POST',
      headers: { Authorization: `Bearer ${env.STRIPE_SECRET}` },
      body: new URLSearchParams(payload as any),
    });
    if (res.status >= 500) throw new Error(`Stripe ${res.status}`);
    return res.json<ChargeResult>();
  });
}
```

Only 5xx responses increment the failure counter. 4xx errors are
the caller's fault — never trip the breaker on them.

## HTTP Response Mapping and Mobile Retry UX

When the breaker is open, return `503` with a `Retry-After` header.
Mobile clients that respect RFC 7231 will back off automatically.

```ts
export async function handlePayment(req: Request, env: Env): Promise<Response> {
  try {
    const result = await chargeCard(env, await req.json());
    return Response.json(result, { status: 200 });
  } catch (err) {
    if (err instanceof BreakerOpenError) {
      return Response.json(
        { error: 'service_unavailable', message: err.message },
        {
          status: 503,
          headers: {
            'Retry-After': String(Math.ceil(err.retryAfterMs / 1000)),
            'X-Circuit-State': 'open',
          },
        },
      );
    }
    throw err;
  }
}
```

| Mobile scenario       | Behaviour without breaker   | Behaviour with breaker      |
|-----------------------|-----------------------------|-----------------------------|
| Payment API down      | 3 retries × 8s timeout = 24s| Instant 503 + Retry-After   |
| D1 overloaded         | Queue of stalled requests   | Fast-fail; queue drains     |
| Half-open probe fails | Flood resumes immediately   | Probe locked 5s; one retry  |
| Recovery detected     | First success only          | Breaker closes; all succeed |

## State Transition Table

| Current state | Event                | Next state  | KV write |
|---------------|----------------------|-------------|----------|
| closed        | success              | closed      | no       |
| closed        | failure < threshold  | closed      | yes      |
| closed        | failure = threshold  | open        | yes      |
| open          | cooldown not elapsed | open        | no       |
| open          | cooldown elapsed     | half-open   | yes      |
| half-open     | probe success        | closed      | yes      |
| half-open     | probe failure        | open        | yes      |
| half-open     | probe already locked | open (hold) | no       |

## Anti-patterns

- **Shared breaker across tenants.** One noisy tenant trips the
  breaker for everyone. Key by `cb:<resource>:<tenantId>`.
- **Counting 4xx as failures.** A client sending bad requests
  should not open a breaker against a healthy API.
- **In-memory state only.** Resets on cold starts and scales
  to zero protection in multi-isolate deployments.
- **No alerting on open.** A breaker opening silently masks an
  outage. Push a log line or metric at state = open.
- **Same threshold for all resources.** A flaky non-critical
  endpoint and a payment endpoint have different risk profiles.

## Gotchas

- KV writes are eventually consistent — a concurrent request may
  read stale closed state for up to ~60ms after the breaker opens.
  Acceptable for soft protection; use a Durable Object for strict
  single-probe guarantees.
- The `expirationTtl: 300` on KV prevents stale `open` entries
  from persisting forever after a resource permanently recovers.
- D1 itself can be the protected resource — do not call D1 inside
  a breaker's KV read path or you create a circular dependency.
  Use a separate KV namespace for breaker state.
- Half-open probe lock is time-based, not transaction-based. Two
  requests can race within the lock window. Accept this at KV
  consistency level; tolerate at most two concurrent probes.

## Verification

```bash
# Trigger 5 failures against a staging resource
for i in $(seq 1 5); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST https://api.example.com/v1/payments/test-fail
done
# 6th request should return 503 with Retry-After
curl -i -X POST https://api.example.com/v1/payments/test-fail | grep -E "503|Retry-After"

# Read KV state directly
wrangler kv key get --binding BREAKERS "cb:stripe-charges"
```

Expected: state = "open", failures = 5, openedAt populated.

After 30s: resubmit one request. Expect half-open probe, then closed
on success or re-open on failure.

## Related

- `circuit-breaker-pattern.md` — generic in-memory pattern reference
- `kv-rate-limiting.md` — KV as edge-persistent counter store
- `retry-with-jitter.md` — compose with breaker for safe retry
- `per-tenant-durable-object.md` — strict single-probe alternative

## Sources

- Martin Fowler, Circuit Breaker: https://martinfowler.com/bliki/CircuitBreaker.html
- Cloudflare KV docs: https://developers.cloudflare.com/kv/
- Release It! — Michael T. Nygard (Chapter 5: Stability Patterns)
