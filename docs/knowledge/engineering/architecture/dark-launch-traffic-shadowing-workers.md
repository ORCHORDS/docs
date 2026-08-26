# Dark Launch — Traffic Shadowing in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You have rewritten a critical HTTP endpoint (a search API, a checkout handler, a pricing
service) and want to validate it under real production traffic before any user sees the new
response. A/B testing is not appropriate because both variants must return the same result;
the goal is to verify correctness and performance, not to measure user preference.

Dark launch (traffic shadowing) solves this: the production Worker forks every request,
sends an identical copy to the new ("dark") service in the background, compares responses,
and logs divergences — all without the user ever seeing the dark response.

---

## Context

Cloudflare Workers are ideal for traffic shadowing because:

- `fetch()` is non-blocking when wrapped in `ctx.waitUntil()`; the shadow call does not
  add latency to the primary response.
- Service bindings provide zero-latency, zero-cost-per-invocation calls to sibling Workers
  in the same account.
- Workers Tail Handlers let you ship divergence events to Analytics Engine or an external
  observability platform without touching the hot path.

Related techniques: canary deployment (subset of users), A/B test (different UX), blue-green
(all-or-nothing cut-over). Dark launch is unique in that the shadow never affects users.

---

## Architecture

```
User → [Primary Worker] → Primary Service → Response to user
              ↓ (ctx.waitUntil, async, silent)
         [Shadow Worker]  → Shadow Service → Response compared & logged (discarded)
```

---

## Implementation

### 1. Shadow Fetch Helper

```typescript
// src/shadow.ts

export interface ShadowResult {
  statusMatch: boolean;
  bodyMatch: boolean;
  primaryStatus: number;
  shadowStatus: number;
  primaryBodyHash: string;
  shadowBodyHash: string;
  shadowLatencyMs: number;
  errorMessage?: string;
}

async function hashBody(body: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(body);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function shadowFetch(
  originalRequest: Request,
  shadowUrl: string,
  primaryResponse: Response,
  primaryBody: string
): Promise<ShadowResult> {
  const start = Date.now();

  // Clone the request, rewrite the URL to the shadow target
  const shadowRequest = new Request(shadowUrl, {
    method: originalRequest.method,
    headers: originalRequest.headers,
    body: originalRequest.body ? originalRequest.clone().body : undefined,
  });

  let shadowResponse: Response;
  let shadowBody = "";
  let errorMessage: string | undefined;

  try {
    shadowResponse = await fetch(shadowRequest);
    shadowBody = await shadowResponse.text();
  } catch (err) {
    errorMessage = String(err);
    return {
      statusMatch: false,
      bodyMatch: false,
      primaryStatus: primaryResponse.status,
      shadowStatus: 0,
      primaryBodyHash: await hashBody(primaryBody),
      shadowBodyHash: "",
      shadowLatencyMs: Date.now() - start,
      errorMessage,
    };
  }

  const [primaryHash, shadowHash] = await Promise.all([
    hashBody(primaryBody),
    hashBody(shadowBody),
  ]);

  return {
    statusMatch: primaryResponse.status === shadowResponse.status,
    bodyMatch: primaryHash === shadowHash,
    primaryStatus: primaryResponse.status,
    shadowStatus: shadowResponse.status,
    primaryBodyHash: primaryHash,
    shadowBodyHash: shadowHash,
    shadowLatencyMs: Date.now() - start,
  };
}
```

---

### 2. Primary Worker with Shadow Logic

```typescript
// src/index.ts

import { shadowFetch, type ShadowResult } from "./shadow";

export interface Env {
  SHADOW_WORKER: Service;      // service binding to the new Worker (same account)
  SHADOW_ENABLED: string;      // KV or plain env var: "true" | "false"
  SHADOW_SAMPLE_RATE: string;  // "0.10" = shadow 10 % of requests
  ANALYTICS: AnalyticsEngineDataset;
}

async function logDivergence(
  env: Env,
  request: Request,
  result: ShadowResult
): Promise<void> {
  env.ANALYTICS.writeDataPoint({
    blobs: [
      request.method,
      new URL(request.url).pathname,
      result.errorMessage ?? "",
    ],
    doubles: [
      result.statusMatch ? 0 : 1,
      result.bodyMatch ? 0 : 1,
      result.shadowLatencyMs,
      result.primaryStatus,
      result.shadowStatus,
    ],
    indexes: [result.bodyMatch ? "match" : "diverge"],
  });
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Serve primary response immediately
    const primaryResponse = await handlePrimary(request, env);
    const primaryBody = await primaryResponse.clone().text();

    // Shadow in background — never blocks the response
    const shadowEnabled = env.SHADOW_ENABLED === "true";
    const sampleRate = parseFloat(env.SHADOW_SAMPLE_RATE ?? "0");

    if (shadowEnabled && Math.random() < sampleRate) {
      ctx.waitUntil(
        (async () => {
          try {
            // Rewrite to shadow Worker via service binding URL
            const shadowUrl = `https://shadow-internal${new URL(request.url).pathname}${new URL(request.url).search}`;
            const result = await shadowFetch(request, shadowUrl, primaryResponse, primaryBody);

            if (!result.bodyMatch || !result.statusMatch) {
              await logDivergence(env, request, result);
            }
          } catch (err) {
            console.error("Shadow error (non-fatal):", err);
          }
        })()
      );
    }

    // Return the primary response to the user unchanged
    return new Response(primaryBody, {
      status: primaryResponse.status,
      headers: primaryResponse.headers,
    });
  },
};

async function handlePrimary(request: Request, env: Env): Promise<Response> {
  // Existing production handler
  return Response.json({ message: "primary response" });
}
```

---

### 3. Shadow Worker (the New Implementation)

The shadow Worker is a normal Worker deployed independently. It should not write to
production state (databases, queues, external APIs). Use a read-only replica or stub
integrations during the dark launch phase.

```typescript
// shadow-worker/src/index.ts

export interface Env {
  DB: D1Database; // may be a staging D1 clone, not production
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // New implementation — should produce equivalent output to primary
    const url = new URL(request.url);
    const id = url.searchParams.get("id") ?? "";
    const row = await env.DB
      .prepare("SELECT * FROM items WHERE id = ?")
      .bind(id)
      .first();
    return Response.json(row ?? {});
  },
};
```

---

### 4. Controlling Shadow Rate at Runtime

Rather than redeploying to change `SHADOW_SAMPLE_RATE`, store it in KV:

```typescript
// In the primary Worker fetch handler:
const rateStr = await env.KV.get("shadow:sample_rate") ?? "0";
const sampleRate = parseFloat(rateStr);
```

Ramp up gradually:

```bash
# Start at 1 %
wrangler kv key put --namespace-id=<NS_ID> shadow:sample_rate 0.01

# After 24 h with no divergences, raise to 10 %
wrangler kv key put --namespace-id=<NS_ID> shadow:sample_rate 0.10

# Full shadow (100 %) before cutting over
wrangler kv key put --namespace-id=<NS_ID> shadow:sample_rate 1.0
```

---

## Divergence Analysis

Query Analytics Engine to surface patterns:

```sql
-- Workers Analytics Engine SQL API
SELECT
  blob1 AS method,
  blob2 AS path,
  SUM(double2) AS body_divergences,
  SUM(double1) AS status_divergences,
  AVG(double3) AS avg_shadow_latency_ms,
  COUNT() AS total_shadowed
FROM analytics_dataset
WHERE timestamp > NOW() - INTERVAL '1' DAY
GROUP BY method, path
ORDER BY body_divergences DESC
```

---

## Anti-patterns

**Letting the shadow write to production state.** If the shadow Worker inserts rows, sends
emails, or charges payments, users will be double-charged or receive duplicate notifications.
Shadow workers must be side-effect-free (read-only or using stub integrations).

**Not sampling.** Running shadow at 100 % from day one doubles compute costs. Start at 1–5 %
to validate the plumbing, then ramp.

**Comparing non-deterministic bodies directly.** Timestamps, UUIDs, and random tokens will
always differ. Normalize responses before hashing:

```typescript
function normalizeForComparison(body: string): string {
  return body
    .replace(/"timestamp":"[^"]+"/g, '"timestamp":"REDACTED"')
    .replace(/"id":"[^"]+"/g, '"id":"REDACTED"');
}
```

**Blocking on the shadow result.** Using `await shadowFetch(...)` outside `ctx.waitUntil`
adds shadow latency to every primary response. Always fire-and-forget.

---

## Gotchas

- Service binding calls (`env.SHADOW_WORKER.fetch(...)`) are free of egress cost but still
  count against the Worker's CPU time budget (50 ms on the Free plan). Use `waitUntil` to
  move shadow work past the response-return checkpoint.
- Request bodies are single-use streams. Clone the request before sending it to the shadow:
  `request.clone()`. Forgetting this causes the primary handler to read an empty body.
- If the primary response body is large (>1 MB), reading it to a string for hashing is
  expensive. Consider hashing incrementally or sampling only the first N bytes for comparison.
- The shadow Worker must be deployed before enabling `SHADOW_ENABLED`; otherwise the service
  binding resolves to a 503.

---

## Verification

```bash
# 1. Deploy shadow Worker
wrangler deploy --config shadow-worker/wrangler.toml

# 2. Enable shadow at 1 %
wrangler kv key put --namespace-id=<NS_ID> shadow:sample_rate 0.01
wrangler kv key put --namespace-id=<NS_ID> shadow:enabled true

# 3. Tail primary Worker for shadow errors
wrangler tail --format pretty | grep -E "shadow|diverge"

# 4. Query Analytics Engine for divergence rate
# (use Workers Analytics Engine SQL API or Cloudflare dashboard)

# 5. Promote to full cut-over when divergence rate = 0 %
wrangler kv key put --namespace-id=<NS_ID> shadow:sample_rate 0
# Update routes / service bindings so primary now calls new Worker directly
```

---

## Related

- `a-b-testing-architecture.md` — when variants should be user-visible
- `canary-deployment-architecture.md` — routing a percentage of real users to a new version
- `workers-versions-api-gradual-rollout.md` — Workers-native gradual rollout mechanism
- `branch-by-abstraction-workers-migration.md` — in-process dual implementation switching
- `chaos-engineering-fault-injection-workers.md` — injecting faults into shadowed traffic

---

## Sources

- Martin Fowler, "DarkLaunching", martinfowler.com/bliki/DarkLaunching.html
- Cloudflare Workers `ctx.waitUntil` — developers.cloudflare.com/workers/runtime-apis/context
- Cloudflare Analytics Engine — developers.cloudflare.com/analytics/analytics-engine
- Cloudflare Service Bindings — developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings
