# Timeout Cascade Prevention Pattern — Workers Fetch

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker calls Service B, which calls Service C, which calls an external API.  When the
external API is slow, every layer waits for the full upstream timeout before propagating
failure.  The originating Worker hits its own 30 s wall-clock limit and returns a 524
to the client.  Worse, if multiple layers are chained without independent timeouts,
the slowest hop determines the total latency for every caller above it.

This is a **timeout cascade**: the lack of per-hop budget means a single slow dependency
consumes the budget of all upstream layers.

---

## Context

Cloudflare Workers have a maximum CPU time (50 ms on the Free plan; no hard wall on
Paid, but wall-clock is capped at 30 s per request including wait time).  Each outbound
`fetch()` counts against that wall-clock budget.  When Workers call other Workers via
service bindings, each hop has its own CPU budget but shares the originating wall-clock
window.

The fix is **deadline propagation**: pass a `deadline` (an absolute expiry time) through
every hop and abort any `fetch()` that cannot complete before the deadline.  Each
intermediate service subtracts its own processing overhead before forwarding the
remaining budget downstream.

---

## Deadline Context Type

```typescript
// src/lib/deadline.ts

export interface DeadlineCtx {
  /** Absolute UNIX milliseconds by which this hop must respond */
  deadlineMs: number;
}

/** Remaining milliseconds until the deadline, clamped to zero */
export function remainingMs(ctx: DeadlineCtx): number {
  return Math.max(0, ctx.deadlineMs - Date.now());
}

/** True if the deadline has already passed */
export function isExpired(ctx: DeadlineCtx): boolean {
  return remainingMs(ctx) === 0;
}

/**
 * Create a child deadline that expires at the earlier of:
 * - The parent's deadline
 * - `maxMs` milliseconds from now
 */
export function childDeadline(parent: DeadlineCtx, maxMs: number): DeadlineCtx {
  return {
    deadlineMs: Math.min(parent.deadlineMs, Date.now() + maxMs),
  };
}

/** Serialise to a header value (UNIX ms as string) */
export function toHeader(ctx: DeadlineCtx): string {
  return String(ctx.deadlineMs);
}

/** Parse from an incoming request header; falls back to `defaultMs` from now */
export function fromRequest(req: Request, defaultMs = 25_000): DeadlineCtx {
  const raw = req.headers.get('x-deadline-ms');
  if (raw !== null) {
    const parsed = parseInt(raw, 10);
    if (!isNaN(parsed)) return { deadlineMs: parsed };
  }
  return { deadlineMs: Date.now() + defaultMs };
}
```

---

## Deadline-Aware Fetch Wrapper

```typescript
// src/lib/timeout-fetch.ts
import { DeadlineCtx, remainingMs } from './deadline';

export class DeadlineExceededError extends Error {
  constructor(url: string, remainMs: number) {
    super(`Deadline exceeded calling ${url}: only ${remainMs}ms remaining`);
    this.name = 'DeadlineExceededError';
  }
}

export interface TimeoutFetchOptions extends RequestInit {
  /** Minimum time budget required to even attempt the call (default: 100 ms) */
  minBudgetMs?: number;
}

/**
 * Wraps `fetch` with an AbortSignal derived from the remaining deadline.
 * Throws DeadlineExceededError immediately when the budget is too thin.
 */
export async function fetchWithDeadline(
  url: string,
  ctx: DeadlineCtx,
  opts: TimeoutFetchOptions = {},
): Promise<Response> {
  const remaining = remainingMs(ctx);
  const minBudget = opts.minBudgetMs ?? 100;

  if (remaining < minBudget) {
    throw new DeadlineExceededError(url, remaining);
  }

  const { minBudgetMs: _, ...fetchOpts } = opts;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), remaining);

  try {
    const res = await fetch(url, {
      ...fetchOpts,
      signal: controller.signal,
    });
    return res;
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new DeadlineExceededError(url, 0);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}
```

---

## Entry Worker (Edge — sets the initial deadline)

```typescript
// src/workers/api-gateway.ts
import { fromRequest, childDeadline, toHeader } from '../lib/deadline';
import { fetchWithDeadline, DeadlineExceededError } from '../lib/timeout-fetch';

export interface Env {
  ORCHESTRATOR: Fetcher; // service binding to next hop
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    // Parse or create a 25 s deadline for the full request
    const ctx = fromRequest(req, 25_000);

    try {
      // Give the orchestrator at most 22 s (reserve 3 s for our own overhead)
      const child = childDeadline(ctx, 22_000);

      const upstreamReq = new Request(req.url, {
        method: req.method,
        headers: {
          ...Object.fromEntries(req.headers),
          'x-deadline-ms': toHeader(child),
        },
        body: req.body,
      });

      return await env.ORCHESTRATOR.fetch(upstreamReq);
    } catch (err) {
      if (err instanceof DeadlineExceededError) {
        return new Response(
          JSON.stringify({ error: 'Gateway timeout', detail: err.message }),
          { status: 504, headers: { 'Content-Type': 'application/json' } },
        );
      }
      throw err;
    }
  },
};
```

---

## Intermediate Worker (reads, narrows, and forwards the deadline)

```typescript
// src/workers/orchestrator.ts
import { fromRequest, childDeadline, toHeader, isExpired } from '../lib/deadline';
import { fetchWithDeadline, DeadlineExceededError } from '../lib/timeout-fetch';

export interface Env {
  DATA_SERVICE_URL: string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const ctx = fromRequest(req); // reads x-deadline-ms from incoming header

    if (isExpired(ctx)) {
      return new Response(JSON.stringify({ error: 'Deadline already passed' }), {
        status: 504,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Reserve 500 ms for local processing; give data service the rest (max 8 s)
    const dataCtx = childDeadline(ctx, Math.min(remainingMs(ctx) - 500, 8_000));
    // Import helper locally
    function remainingMs(c: typeof ctx) { return Math.max(0, c.deadlineMs - Date.now()); }

    try {
      const res = await fetchWithDeadline(
        `${env.DATA_SERVICE_URL}/query`,
        dataCtx,
        {
          method: 'POST',
          body: req.body,
          headers: {
            'Content-Type': 'application/json',
            'x-deadline-ms': toHeader(dataCtx),
          },
        },
      );

      return new Response(res.body, {
        status: res.status,
        headers: res.headers,
      });
    } catch (err) {
      if (err instanceof DeadlineExceededError) {
        return new Response(JSON.stringify({ error: 'Upstream timeout' }), {
          status: 504,
          headers: { 'Content-Type': 'application/json' } ,
        });
      }
      throw err;
    }
  },
};
```

---

## Leaf Worker (honours the deadline for external calls)

```typescript
// src/workers/data-service.ts
import { fromRequest } from '../lib/deadline';
import { fetchWithDeadline } from '../lib/timeout-fetch';

const EXTERNAL_API = 'https://api.example.com/data';

export default {
  async fetch(req: Request): Promise<Response> {
    const ctx = fromRequest(req);

    // Use whatever budget remains (the upstream already narrowed it)
    const data = await fetchWithDeadline(EXTERNAL_API, ctx, {
      method: 'GET',
      headers: { Authorization: `Bearer ${(req as Request & { env?: { TOKEN?: string } }).env?.TOKEN ?? ''}` },
      // Give external API at most 5 s regardless of remaining budget
      minBudgetMs: 200,
    });

    return new Response(data.body, {
      status: data.status,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

---

## Observability: Logging Remaining Budget

```typescript
// Middleware: log remaining budget at each hop for timeout analysis

function withDeadlineLogging(handler: ExportedHandlerFetchHandler): ExportedHandlerFetchHandler {
  return async (req, env, ctx) => {
    const deadline = fromRequest(req);
    const remaining = Math.max(0, deadline.deadlineMs - Date.now());
    console.log('Request start', {
      remainingMs: remaining,
      url: req.url,
      worker: (env as { WORKER_NAME?: string }).WORKER_NAME ?? 'unknown',
    });
    const res = await handler(req, env, ctx);
    const remainingAfter = Math.max(0, deadline.deadlineMs - Date.now());
    console.log('Request end', { consumedMs: remaining - remainingAfter, status: res.status });
    return res;
  };
}
```

---

## Anti-patterns

- **Per-service hardcoded timeouts** — `fetch(url, { signal: AbortSignal.timeout(5000) })`
  at every layer ignores the upstream budget; a 5 s leaf timeout added to a 5 s
  orchestrator timeout gives 10 s, blowing past a 7 s gateway SLA.
- **No minimum budget check** — attempting a `fetch` with 10 ms remaining guarantees an
  abort; pay the fast-fail cost before the network round-trip.
- **Swallowing `AbortError`** — catching all errors and returning a generic 500 hides
  timeouts from monitoring; always map `AbortError` to 504 with logging.
- **Forwarding the full parent deadline unchanged** — the intermediate service should
  always subtract its own processing budget before forwarding; otherwise one slow
  computation in the middle eats the leaf's entire window.
- **Not propagating the deadline on retry** — if you retry a failed call, recompute the
  remaining budget; a retry using the original deadline may have zero time left.

---

## Gotchas

- **`AbortSignal.timeout(n)`** was added to the Web Platform; Workers support it, but
  it cannot be cancelled, unlike `AbortController.signal`.  Use `AbortController` when
  you need `clearTimeout`.
- **Service binding latency** is ~0 ms CPU to ~1 ms wall-clock; budget for it when
  computing child deadlines in tight chains.
- **Workers wall-clock limit is 30 s** — any chain of Workers that runs longer than 30 s
  from the edge entry will get a Cloudflare 524; set your root deadline to ≤ 25 s to
  leave buffer.
- **`fetch` on a service binding ignores `signal` in some runtime versions** — test that
  the abort actually fires when calling internal bindings, not just external URLs.
- **Clock skew** — `Date.now()` in different Workers invocations on different machines
  can diverge by a few milliseconds; treat the deadline as an approximation, not a
  hard guarantee.

---

## Verification

```typescript
// Simulate slow upstream and assert 504 propagation
const mockSlow = (ms: number) =>
  new Promise<Response>(resolve => setTimeout(
    () => resolve(new Response('ok')), ms,
  ));

it('aborts fetch when budget is exceeded', async () => {
  const ctx = { deadlineMs: Date.now() + 50 }; // only 50 ms
  await expect(
    fetchWithDeadline('https://httpbin.org/delay/5', ctx),
  ).rejects.toThrow('Deadline exceeded');
});

it('throws immediately when budget is below minimum', async () => {
  const ctx = { deadlineMs: Date.now() + 50 };
  await expect(
    fetchWithDeadline('https://example.com', ctx, { minBudgetMs: 200 }),
  ).rejects.toThrow('Deadline exceeded');
});
```

---

## Related

- `circuit-breaker-workers-d1-fetch.md` — fail-fast on sustained upstream errors
- `exponential-backoff-jitter-workers.md` — retry strategy respecting remaining budget
- `bulkhead-pattern-workers-subrequests.md` — isolate slow dependencies
- `request-hedging-latency.md` — parallel speculative requests as a timeout complement

---

## Sources

- "The Deadline Propagation Pattern" — Google SRE Workbook ch. 22
  https://sre.google/workbook/
- Cloudflare Workers limits — CPU and wall-clock time
  https://developers.cloudflare.com/workers/platform/limits/
- `AbortSignal.timeout` — MDN
  https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/timeout_static
