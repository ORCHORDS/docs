# Workers: fetch() Without AbortSignal Causes 30-Second Hangs

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker calling a slow third-party upstream API via `fetch()` with no timeout configured was silently hanging for the full 30-second Cloudflare Worker wall-clock limit before returning a 524 error to the client. Under moderate traffic, this exhausted the Worker's concurrent request capacity and caused cascading latency spikes across unrelated endpoints.

## Context

- Cloudflare Workers (no Durable Objects involved)
- TypeScript, Wrangler v3
- Upstream: third-party enrichment API with p99 latency normally under 800 ms
- Incident: upstream had a partial outage with requests hanging at the TCP connect level
- Incident date: 2026-08-16; lasted ~25 minutes before upstream recovered
- During incident: 100% of requests touching the enrichment path returned 524

## Timeline

1. 16:00 UTC — Upstream enrichment API begins hanging TCP connections (their incident)
2. 16:01 UTC — First 524 errors observed in Cloudflare analytics
3. 16:02 UTC — Worker CPU metric flat (Workers not CPU-bound, they're stuck in I/O wait)
4. 16:05 UTC — Error rate 100% on `/enrich` path; other paths begin degrading due to concurrency starvation
5. 16:07 UTC — On-call paged; team confirms upstream is at fault via status page
6. 16:25 UTC — Upstream recovers; errors clear
7. 16:30 UTC — Post-incident: `AbortSignal.timeout()` added to all outbound `fetch()` calls

## Root Cause

Cloudflare Workers do not impose a per-`fetch()` timeout. The only wall-clock limit is the overall Worker execution time (30 seconds for paid plans). A `fetch()` that never receives a response from the upstream will block the Worker's event loop for up to 30 seconds, consuming one of the Worker's concurrent execution slots.

```typescript
// Problematic code — no timeout
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // If upstream hangs, this awaits for up to 30 seconds
    const upstream = await fetch('https://slow-api.example.com/enrich', {
      method: 'POST',
      body: request.body,
    });
    return upstream;
  },
};
```

When many requests accumulate in this state, the Cloudflare Worker runtime begins queuing new requests, which then also time out waiting for a slot — cascading the failure.

## Fix

### Option A: `AbortSignal.timeout()` (recommended)

```typescript
// src/handlers/enrich.ts
export async function handleEnrich(
  request: Request,
  env: Env
): Promise<Response> {
  // Abort the upstream fetch after 5 seconds
  const signal = AbortSignal.timeout(5_000);

  let upstream: Response;
  try {
    upstream = await fetch('https://slow-api.example.com/enrich', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: request.body,
      signal, // attach abort signal
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'TimeoutError') {
      return new Response(
        JSON.stringify({ error: 'upstream_timeout', retryable: true }),
        { status: 504, headers: { 'Content-Type': 'application/json' } }
      );
    }
    throw err; // rethrow unexpected errors
  }

  if (!upstream.ok) {
    return new Response(
      JSON.stringify({ error: 'upstream_error', status: upstream.status }),
      { status: 502, headers: { 'Content-Type': 'application/json' } }
    );
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: upstream.headers,
  });
}
```

### Option B: `Promise.race` with manual timeout (fallback for older runtimes)

```typescript
// src/utils/fetch-with-timeout.ts
export function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = 5_000
): Promise<Response> {
  const controller = new AbortController();

  const timeoutId = setTimeout(() => {
    controller.abort(new DOMException('Request timed out', 'TimeoutError'));
  }, timeoutMs);

  return fetch(url, { ...options, signal: controller.signal }).finally(() => {
    clearTimeout(timeoutId);
  });
}

// Usage
export async function handleEnrich(
  request: Request,
  env: Env
): Promise<Response> {
  try {
    const upstream = await fetchWithTimeout(
      'https://slow-api.example.com/enrich',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: request.body,
      },
      5_000 // 5-second timeout
    );
    return upstream;
  } catch (err) {
    const isTimeout =
      err instanceof DOMException && err.name === 'TimeoutError';
    return new Response(
      JSON.stringify({
        error: isTimeout ? 'upstream_timeout' : 'upstream_error',
        retryable: isTimeout,
      }),
      { status: isTimeout ? 504 : 502, headers: { 'Content-Type': 'application/json' } }
    );
  }
}
```

## Prevention

### Lint rule: ban bare `fetch()` without signal in Worker source

```typescript
// scripts/lint-fetch-timeout.ts — run in CI
import { parse, TSESTree } from '@typescript-eslint/typescript-estree';
import * as fs from 'fs';
import * as glob from 'glob';

const files = glob.sync('src/**/*.ts');
let violations = 0;

for (const file of files) {
  const src = fs.readFileSync(file, 'utf8');
  const ast = parse(src, { range: true, loc: true });

  // Heuristic: find await fetch( calls that are not preceded by AbortSignal
  // Real implementation would use AST traversal; this is a fast regex check
  const fetchCalls = [...src.matchAll(/await fetch\s*\(/g)];
  for (const match of fetchCalls) {
    const snippet = src.slice(match.index ?? 0, (match.index ?? 0) + 500);
    if (!snippet.includes('signal')) {
      const line = src.slice(0, match.index).split('\n').length;
      console.error(`[lint-fetch-timeout] ${file}:${line}: fetch() missing 'signal' option — add AbortSignal.timeout()`);
      violations++;
    }
  }
}

if (violations > 0) process.exit(1);
console.log('[lint-fetch-timeout] All fetch() calls have timeout signals');
```

### Shared fetch utility with mandatory timeout

```typescript
// src/utils/http.ts

const DEFAULT_TIMEOUT_MS = 8_000;

export interface FetchOptions extends RequestInit {
  timeoutMs?: number;
}

export async function safeFetch(
  url: string,
  options: FetchOptions = {}
): Promise<Response> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options;

  // Merge any existing signal with timeout signal
  const signals = [AbortSignal.timeout(timeoutMs)];
  if (fetchOptions.signal) {
    signals.push(fetchOptions.signal as AbortSignal);
  }

  // AbortSignal.any() aborts when ANY signal fires (available in modern runtimes)
  const signal = (AbortSignal as any).any
    ? (AbortSignal as any).any(signals)
    : signals[0];

  return fetch(url, { ...fetchOptions, signal });
}
```

## Anti-patterns

- Calling `await fetch(url)` or `await fetch(url, { method, body, headers })` without a `signal` property
- Setting a timeout only on the Worker as a whole (30 s) and assuming that is sufficient for upstream calls
- Using `setTimeout` + `Promise.race` without using `AbortController` — the fetch still runs in the background consuming resources even after the race resolves
- Swallowing `DOMException` errors generically without distinguishing `TimeoutError` from other abort causes
- Not returning a `504` or `502` to the client with a `retryable` hint when upstream times out

## Gotchas

- `AbortSignal.timeout()` is supported in the Cloudflare Workers runtime (V8-based); verify your `compatibility_date` is recent enough
- Aborting a `fetch()` does not cancel the upstream request from the upstream server's perspective — it only stops the Worker from waiting
- Multiple `fetch()` calls to the same upstream within one request should each get their own `AbortSignal.timeout()` with appropriate per-call budgets
- Workers running in `DurableObject.fetch()` share the same 30-second wall-clock limit
- Setting `compatibility_date = "2023-03-01"` or later in `wrangler.toml` enables `AbortSignal.timeout` in the Workers runtime

## Verification

```bash
# Simulate a slow upstream locally with a mock server
npx tsx scripts/slow-mock-server.ts &  # listens on :9999, delays all responses 10s

# Run the Worker locally pointing at the mock
npx wrangler dev --local &

# Hit the enrich endpoint — should return 504 within ~5 seconds, not 30
time curl -s -o /dev/null -w '%{http_code}' http://localhost:8787/enrich
# Expected output: 504 (within ~5 seconds)

# Run unit tests
npx vitest run tests/unit/fetch-timeout.test.ts

# Lint check
ts-node scripts/lint-fetch-timeout.ts
```

```typescript
// tests/unit/fetch-timeout.test.ts
import { describe, it, expect, vi } from 'vitest';
import { safeFetch } from '../../src/utils/http';

describe('safeFetch', () => {
  it('throws TimeoutError when upstream is slow', async () => {
    // Mock fetch to never resolve
    vi.stubGlobal('fetch', () => new Promise(() => {}));

    await expect(safeFetch('https://example.com', { timeoutMs: 100 }))
      .rejects
      .toMatchObject({ name: 'TimeoutError' });
  });
});
```

## Related

- `lessons-durable-objects-concurrent-fetch-deadlock.md` — DO fetch patterns
- `lessons-queues-consumer-exception-infinite-retry.md` — Handling downstream failures

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/fetch/
- https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/timeout_static
- https://developers.cloudflare.com/workers/platform/limits/#worker-limits
- https://developers.cloudflare.com/workers/runtime-apis/request/#signal
