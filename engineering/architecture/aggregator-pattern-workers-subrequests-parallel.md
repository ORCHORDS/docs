# Aggregator Pattern with Workers Parallel Subrequests

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A client needs a composite response assembled from multiple upstream services—user profile, account balance, recent activity, and feature flags—but calling them sequentially inflates tail latency to the sum of individual RTTs. You need a single edge Worker that fans out to all origins in parallel, merges the results, and returns a unified payload within a tight latency budget.

## Context

The aggregator pattern places a single coordinator between the client and N upstream services. In a Cloudflare Workers context the coordinator issues all subrequests with `Promise.all` (or `Promise.allSettled` for partial-failure tolerance), merges the responses, and returns a single JSON object. Workers can make up to 50 subrequests per invocation on paid plans and benefit from Cloudflare's anycast network for low-latency origin fetches. For large N or variable-latency upstreams, a timeout fence ensures the aggregator never blocks indefinitely on a slow service.

## Parallel Fetch with Timeout Fence

Issue all subrequests concurrently and race each one against a per-service timeout. Use `Promise.allSettled` so a single slow or failing upstream does not block the entire response.

```typescript
// src/aggregator.ts
interface AggregatedProfile {
  user: unknown | null;
  balance: unknown | null;
  activity: unknown | null;
  flags: unknown | null;
  errors: string[];
}

const SERVICE_TIMEOUT_MS = 800;

function fetchWithTimeout(url: string, timeout: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  return fetch(url, { signal: controller.signal }).finally(() =>
    clearTimeout(timer)
  );
}

async function safeJson<T>(
  label: string,
  promise: Promise<Response>
): Promise<{ label: string; data: T | null; error: string | null }> {
  try {
    const res = await promise;
    if (!res.ok) {
      return { label, data: null, error: `HTTP ${res.status}` };
    }
    const data: T = await res.json();
    return { label, data, error: null };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { label, data: null, error: message };
  }
}

export async function aggregate(userId: string): Promise<AggregatedProfile> {
  const [userR, balanceR, activityR, flagsR] = await Promise.all([
    safeJson<unknown>(
      "user",
      fetchWithTimeout(`https://users.internal/users/${userId}`, SERVICE_TIMEOUT_MS)
    ),
    safeJson<unknown>(
      "balance",
      fetchWithTimeout(`https://billing.internal/balance/${userId}`, SERVICE_TIMEOUT_MS)
    ),
    safeJson<unknown>(
      "activity",
      fetchWithTimeout(`https://events.internal/activity/${userId}?limit=10`, SERVICE_TIMEOUT_MS)
    ),
    safeJson<unknown>(
      "flags",
      fetchWithTimeout(`https://flags.internal/evaluate/${userId}`, SERVICE_TIMEOUT_MS)
    ),
  ]);

  const results = [userR, balanceR, activityR, flagsR];
  const errors = results
    .filter((r) => r.error !== null)
    .map((r) => `${r.label}: ${r.error}`);

  return {
    user: userR.data,
    balance: balanceR.data,
    activity: activityR.data,
    flags: flagsR.data,
    errors,
  };
}
```

## Worker Entry Point with Cache Layer

Cache the aggregated response for a short TTL to absorb burst traffic. Use `caches.default` with a surrogate key so downstream invalidation can purge by user without a full cache bust.

```typescript
// src/worker.ts
interface Env {
  AGGREGATION_KV: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const userId = url.searchParams.get("userId");
    if (!userId) {
      return new Response("Missing userId", { status: 400 });
    }

    const cacheKey = `agg:${userId}`;
    const cached = await env.AGGREGATION_KV.get(cacheKey, "json");
    if (cached) {
      return Response.json(cached, {
        headers: { "X-Cache": "HIT" },
      });
    }

    const { aggregate } = await import("./aggregator");
    const payload = await aggregate(userId);

    // Cache for 5 seconds — short enough to stay fresh, long enough to absorb bursts
    await env.AGGREGATION_KV.put(cacheKey, JSON.stringify(payload), {
      expirationTtl: 5,
    });

    const status = payload.errors.length > 0 ? 207 : 200;
    return Response.json(payload, {
      status,
      headers: { "X-Cache": "MISS" },
    });
  },
} satisfies ExportedHandler<Env>;
```

## Partial-Failure Handling and Degraded Responses

When an upstream is unavailable, return a degraded but usable response rather than a 502. Signal partial failures with an HTTP 207 and an `errors` array so clients can decide whether to render partial data or retry.

```typescript
// src/handlers/render-profile.ts
async function renderProfile(userId: string): Promise<Response> {
  const res = await fetch(`https://aggregator.workers.dev/?userId=${userId}`);
  const body = await res.json<{ user: unknown; balance: unknown; errors: string[] }>();

  if (!body.user) {
    // Core data missing — hard failure
    return new Response("Profile unavailable", { status: 503 });
  }

  // Render with whatever data arrived; surface warnings for missing sections
  const html = buildHtml(body.user, body.balance, body.errors);
  return new Response(html, {
    headers: { "Content-Type": "text/html" },
  });
}

function buildHtml(user: unknown, balance: unknown, errors: string[]): string {
  const warnings = errors.map((e) => `<li>${e}</li>`).join("");
  return `<h1>Profile</h1><pre>${JSON.stringify(user, null, 2)}</pre>
    ${balance ? `<pre>${JSON.stringify(balance, null, 2)}</pre>` : "<p>Balance unavailable</p>"}
    ${warnings ? `<ul class="warnings">${warnings}</ul>` : ""}`;
}
```

## Anti-patterns

- Chaining subrequests sequentially when they have no data dependency—always use `Promise.all` for independent fetches.
- Omitting per-service timeouts and relying on the Worker's global 30-second CPU limit—a slow upstream can starve the response for other users.
- Aggregating more than ~20 services in a single Worker invocation without a scatter-gather Durable Object intermediary; the subrequest limit and memory pressure become practical concerns.

## Gotchas

- Cloudflare Workers on the free plan allow only 50 subrequests per invocation; exceeding this throws a runtime error—count bindings, Service Bindings, and external fetches together.
- `AbortController` signals are respected by `fetch` but not by Service Bindings; for DO stubs, wrap the call in a `Promise.race` with a timeout rejection.

## Verification

```bash
# Run aggregator and inspect partial failures
curl -s "https://your-worker.workers.dev/?userId=user-123" | jq '{status: .errors | length, errors: .errors}'

# Measure parallel vs sequential latency
time curl -s "https://your-worker.workers.dev/?userId=user-123" > /dev/null
```

## Related

- `architecture/api-gateway-pattern-cloudflare-workers.md`
- `architecture/workers-queue-fanout-architecture.md`
- `architecture/event-driven-fanout-patterns.md`
- `architecture/backend-for-frontend-pattern.md`

## Sources

- https://developers.cloudflare.com/workers/platform/limits/#subrequests
- https://developers.cloudflare.com/workers/runtime-apis/fetch/
- https://microservices.io/patterns/data/api-composition.html
