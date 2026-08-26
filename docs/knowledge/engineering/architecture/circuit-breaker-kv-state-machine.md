# Circuit Breaker State Machine with KV

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Cloudflare Worker calls a third-party payment API on every checkout request. The API degrades
for 5 minutes during peak hours, returning 503s. Without a circuit breaker, every user request
waits for the full upstream timeout (up to 30 seconds), exhausting the Worker's subrequest budget
and creating cascading failures. A circuit breaker detects the failure pattern early, returns a
fast fallback immediately, and automatically restores normal operation once the API recovers.

## Context

A classic circuit breaker has three states:

- **Closed** (normal): requests flow through; failures are counted.
- **Open** (tripped): requests are rejected immediately without calling the upstream.
- **Half-Open** (probing): a single test request is allowed through; success closes the circuit,
  failure reopens it.

Implementing this in Cloudflare Workers requires shared mutable state across all isolates at a
given edge location. KV is the right tool: it provides fast reads (cached at the edge) and
acceptably consistent writes for breaker state transitions. Durable Objects provide stronger
consistency guarantees if strict serialisation is needed (see Gotchas).

The state machine is stored in a single KV key per circuit, with a short TTL to auto-expire open
circuits and force half-open probes.

## State Schema

```typescript
// circuit-breaker.ts
export type CircuitState = "closed" | "open" | "half-open";

export interface BreakerRecord {
  state: CircuitState;
  failures: number;           // consecutive failure count
  lastFailureAt: number;      // epoch ms
  successesInHalfOpen: number;
  updatedAt: number;
}

export const DEFAULTS = {
  failureThreshold: 5,        // trips open after N consecutive failures
  openWindowMs: 30_000,       // stay open for 30 s, then become half-open
  halfOpenSuccessThreshold: 2, // consecutive successes needed to close
  kvTtlSeconds: 120,          // KV entry TTL — auto-delete closed circuits
};
```

## Core State Machine Logic

```typescript
// circuit-breaker.ts (continued)
export async function getBreaker(
  kv: KVNamespace,
  key: string
): Promise<BreakerRecord> {
  const raw = await kv.get<BreakerRecord>(key, "json");
  if (!raw) {
    return {
      state: "closed",
      failures: 0,
      lastFailureAt: 0,
      successesInHalfOpen: 0,
      updatedAt: Date.now(),
    };
  }

  // Transition open → half-open when the window expires.
  if (raw.state === "open" && Date.now() - raw.lastFailureAt > DEFAULTS.openWindowMs) {
    return { ...raw, state: "half-open", updatedAt: Date.now() };
  }

  return raw;
}

export async function recordSuccess(
  kv: KVNamespace,
  key: string,
  current: BreakerRecord
): Promise<BreakerRecord> {
  let next: BreakerRecord;

  if (current.state === "half-open") {
    const successes = current.successesInHalfOpen + 1;
    next = successes >= DEFAULTS.halfOpenSuccessThreshold
      ? { ...current, state: "closed", failures: 0, successesInHalfOpen: 0, updatedAt: Date.now() }
      : { ...current, successesInHalfOpen: successes, updatedAt: Date.now() };
  } else {
    // Closed: reset failure count on success.
    next = { ...current, failures: 0, updatedAt: Date.now() };
  }

  await kv.put(key, JSON.stringify(next), { expirationTtl: DEFAULTS.kvTtlSeconds });
  return next;
}

export async function recordFailure(
  kv: KVNamespace,
  key: string,
  current: BreakerRecord
): Promise<BreakerRecord> {
  const failures = current.failures + 1;
  const trips = failures >= DEFAULTS.failureThreshold || current.state === "half-open";
  const next: BreakerRecord = {
    ...current,
    state: trips ? "open" : "closed",
    failures,
    lastFailureAt: Date.now(),
    successesInHalfOpen: 0,
    updatedAt: Date.now(),
  };

  await kv.put(key, JSON.stringify(next), { expirationTtl: DEFAULTS.kvTtlSeconds });
  return next;
}
```

## Integration in a Worker Handler

```typescript
// worker.ts
import { getBreaker, recordSuccess, recordFailure } from "./circuit-breaker";

const CIRCUIT_KEY = "circuit:payment-api";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (new URL(request.url).pathname !== "/checkout") {
      return new Response("Not Found", { status: 404 });
    }

    // 1. Read breaker state.
    const breaker = await getBreaker(env.BREAKER_KV, CIRCUIT_KEY);

    if (breaker.state === "open") {
      return Response.json(
        { error: "Payment service temporarily unavailable. Please try again shortly." },
        {
          status: 503,
          headers: {
            "Retry-After": "30",
            "X-Circuit-State": "open",
          },
        }
      );
    }

    if (breaker.state === "half-open") {
      // Only let one probe through — simple probabilistic guard.
      // A Durable Object mutex is preferable for strict single-probe guarantees.
      const probe = Math.random() < 0.1; // 10% of requests probe when half-open
      if (!probe) {
        return Response.json(
          { error: "Payment service recovering. Please try again shortly." },
          { status: 503, headers: { "X-Circuit-State": "half-open" } }
        );
      }
    }

    // 2. Call upstream.
    let upstreamRes: Response;
    try {
      upstreamRes = await fetch("https://payments.example.com/charge", {
        method: "POST",
        body: request.body,
        headers: { Authorization: `Bearer ${env.PAYMENT_KEY}` },
        signal: AbortSignal.timeout(5_000),
      });
    } catch (err) {
      // Network error or timeout — record as failure.
      await recordFailure(env.BREAKER_KV, CIRCUIT_KEY, breaker);
      return Response.json({ error: "Payment service unreachable" }, { status: 502 });
    }

    if (upstreamRes.status >= 500) {
      await recordFailure(env.BREAKER_KV, CIRCUIT_KEY, breaker);
      return Response.json(
        { error: "Payment service error" },
        { status: 502, headers: { "X-Circuit-State": breaker.state } }
      );
    }

    // 3. Success — reset failure count (or close if half-open).
    await recordSuccess(env.BREAKER_KV, CIRCUIT_KEY, breaker);
    const data = await upstreamRes.json();
    return Response.json(data, { status: upstreamRes.status });
  },
} satisfies ExportedHandler<Env>;
```

`wrangler.toml`:

```toml
[[kv_namespaces]]
binding = "BREAKER_KV"
id = "YOUR_KV_NAMESPACE_ID"
```

## Admin Endpoint — Manual Circuit Control

```typescript
// admin.ts — force open/close a circuit for maintenance
export async function handleAdmin(request: Request, env: Env): Promise<Response> {
  const { circuit, action } = await request.json<{ circuit: string; action: "open" | "close" | "reset" }>();

  if (action === "open") {
    const current = await getBreaker(env.BREAKER_KV, circuit);
    await recordFailure(env.BREAKER_KV, circuit, {
      ...current,
      failures: DEFAULTS.failureThreshold, // Immediately trip
    });
    return Response.json({ ok: true, state: "open" });
  }

  if (action === "close" || action === "reset") {
    await env.BREAKER_KV.delete(circuit); // Deleting resets to closed default
    return Response.json({ ok: true, state: "closed" });
  }

  return Response.json({ error: "unknown action" }, { status: 400 });
}
```

## Anti-patterns

- **Counting all errors**: Only count errors that indicate upstream unavailability (5xx, timeouts).
  4xx errors (bad request, auth failure) are the caller's fault and should not trip the circuit.
- **Single global circuit for all tenants**: A single tenant hammering an API should not open the
  circuit for all tenants. Use per-tenant circuit keys: `circuit:payment-api:${tenantId}`.
- **Synchronous state writes blocking the user response**: `recordSuccess` and `recordFailure`
  write to KV. For ultra-low-latency paths, move these to `event.waitUntil()` so the KV write
  does not add latency to the response.
- **Hardcoded thresholds**: Failure thresholds that work at low traffic (5 failures in 10 req/s)
  are too sensitive at high traffic (5 failures in 10 000 req/s is noise). Use failure *rate*
  (failures / total in a sliding window) instead of absolute counts for high-traffic circuits.

## Gotchas

- KV has eventual consistency with ~60 ms read-after-write propagation. Two Workers reading the
  circuit state within milliseconds of a state transition may both see the old state. For strict
  serialisation (exactly one probe in half-open), use a Durable Object instead of KV.
- KV `put()` calls from Workers count against the KV write limit (1 write/second per key for
  free plans). Use Workers Paid for high-frequency state updates or batch transitions.
- `AbortSignal.timeout()` is available in Workers runtime v3+. On older runtimes use a manual
  `Promise.race()` with a `setTimeout` wrapped in a Promise.
- The `expirationTtl` on KV entries means a closed circuit with no traffic will automatically
  expire and revert to default state. This is desirable — a circuit that sees no traffic is
  effectively closed. Adjust TTL if you need the state to persist across idle periods.

## Verification

```bash
# Observe circuit transitions:
watch -n 1 "wrangler kv key get --binding=BREAKER_KV 'circuit:payment-api'"

# Simulate 10 upstream failures to trip the breaker:
for i in $(seq 1 10); do
  curl -X POST https://your-worker.example.com/checkout \
    -d '{"amount":1000}' -s -o /dev/null -w "HTTP %{http_code}\n"
done

# Observe open state:
curl -X POST https://your-worker.example.com/checkout \
  -d '{"amount":1000}' -i
# Expect: HTTP/1.1 503, Retry-After: 30, X-Circuit-State: open

# Wait 30s for half-open probe window:
sleep 30
curl -X POST https://your-worker.example.com/checkout -d '{"amount":1000}' -i
```

## Related

- `circuit-breaker-design.md`
- `circuit-breaker.md`
- `retry-pattern.md`
- `timeout-pattern.md`
- `bulkhead-pattern.md`
- `fallback-pattern.md`
- `rate-limiting-architecture-workers.md`

## Sources

- Michael Nygard, "Release It!" — Circuit Breaker pattern
- Martin Fowler, "CircuitBreaker" — https://martinfowler.com/bliki/CircuitBreaker.html
- Cloudflare KV documentation — https://developers.cloudflare.com/kv/
- Workers AbortSignal.timeout() — https://developers.cloudflare.com/workers/runtime-apis/request/#abortsignal
