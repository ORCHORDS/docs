# Cloudflare Workers Subrequest Budget Management

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Cloudflare Worker handling complex API orchestration begins throwing `Error: Too many subrequests` in production with no obvious change in application logic. Investigation reveals that a recursive fetch chain or fan-out pattern silently accumulated subrequests across middleware layers, eventually breaching the platform's 1000-subrequest limit per invocation. Without explicit budget tracking, subrequest exhaustion is only discovered at runtime under load.

## Context

Cloudflare Workers enforce a hard limit of 1000 subrequests per Worker invocation on the Paid plan (50 on the Free plan). A "subrequest" includes every outbound `fetch()` call, every KV read/write, every D1 query, every R2 operation, and every Durable Object stub call. In an orchestration Worker that aggregates multiple upstream APIs, fans out to D1 for enrichment, and then writes results to R2, it is straightforward to exhaust this budget under unexpected load patterns such as pagination loops or recursive retry logic. The Workers runtime does not surface the remaining budget in a first-class API; teams must instrument it manually using a lightweight context-threaded counter.

## Implementing a Subrequest Budget Context

Thread a mutable budget object through the request context so every subsystem can charge against it and check headroom before making calls.

```typescript
// types/budget.ts
export interface SubrequestBudget {
  used: number;
  limit: number;
  reserve(n?: number): void;
  remaining(): number;
}

export function createBudget(limit = 950): SubrequestBudget {
  // Use 950 as the safe ceiling; leave 50 for error handling paths
  let used = 0;
  return {
    get used() {
      return used;
    },
    limit,
    reserve(n = 1) {
      used += n;
      if (used > limit) {
        throw new BudgetExhaustedError(
          `Subrequest budget exhausted: used ${used} of ${limit}`
        );
      }
    },
    remaining() {
      return limit - used;
    },
  };
}

export class BudgetExhaustedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BudgetExhaustedError";
  }
}
```

```typescript
// lib/fetch-with-budget.ts
import type { SubrequestBudget } from "../types/budget";

export async function fetchWithBudget(
  budget: SubrequestBudget,
  input: RequestInfo,
  init?: RequestInit
): Promise<Response> {
  budget.reserve(1);
  const response = await fetch(input, init);
  return response;
}

// lib/d1-with-budget.ts
export async function queryD1<T>(
  budget: SubrequestBudget,
  stmt: D1PreparedStatement
): Promise<D1Result<T>> {
  budget.reserve(1); // D1 prepared statement execution = 1 subrequest
  return stmt.all<T>();
}

// lib/kv-with-budget.ts
export async function kvGet(
  budget: SubrequestBudget,
  kv: KVNamespace,
  key: string
): Promise<string | null> {
  budget.reserve(1);
  return kv.get(key);
}
```

## Fan-out Guard and Parallel Request Batching

Fan-out patterns (fetching N upstream services in parallel) are common but risky. Wrap parallel fetch with a gate that checks remaining budget before dispatching.

```typescript
// lib/fanout.ts
import { fetchWithBudget } from "./fetch-with-budget";
import type { SubrequestBudget } from "../types/budget";

interface FanoutRequest {
  url: string;
  init?: RequestInit;
}

export async function fanout(
  budget: SubrequestBudget,
  requests: FanoutRequest[],
  options: { maxConcurrent?: number } = {}
): Promise<Response[]> {
  const { maxConcurrent = 10 } = options;

  if (requests.length > budget.remaining()) {
    throw new Error(
      `Fan-out of ${requests.length} requests would exceed remaining budget of ${budget.remaining()}`
    );
  }

  const results: Response[] = [];
  // Process in chunks to avoid both budget exhaustion and TCP connection exhaustion
  for (let i = 0; i < requests.length; i += maxConcurrent) {
    const chunk = requests.slice(i, i + maxConcurrent);
    const chunkResults = await Promise.all(
      chunk.map((req) => fetchWithBudget(budget, req.url, req.init))
    );
    results.push(...chunkResults);
  }
  return results;
}
```

## Subrequest Budget Middleware and Observability

Attach budget tracking to the request lifecycle via middleware and emit the final usage as a metric for trending.

```typescript
// middleware/budget-middleware.ts
import { createBudget, BudgetExhaustedError } from "../types/budget";
import type { SubrequestBudget } from "../types/budget";

export interface RequestContext {
  budget: SubrequestBudget;
  requestId: string;
}

export async function withBudget<Env>(
  request: Request,
  env: Env & { METRICS_QUEUE?: Queue },
  handler: (ctx: RequestContext) => Promise<Response>
): Promise<Response> {
  const budget = createBudget(950);
  const requestId = crypto.randomUUID();
  const start = Date.now();

  try {
    const response = await handler({ budget, requestId });

    // Emit usage as a non-blocking side channel
    const headers = new Headers(response.headers);
    headers.set("X-Subrequest-Used", String(budget.used));
    headers.set("X-Subrequest-Remaining", String(budget.remaining()));

    // Async metric without consuming additional budget
    if (env.METRICS_QUEUE && budget.used > 500) {
      // Only log high-usage requests to reduce queue pressure
      env.METRICS_QUEUE.send({
        type: "subrequest_usage",
        requestId,
        used: budget.used,
        limit: budget.limit,
        durationMs: Date.now() - start,
        path: new URL(request.url).pathname,
      }).catch(() => {}); // Fire-and-forget; never throw from observability
    }

    return new Response(response.body, {
      status: response.status,
      headers,
    });
  } catch (err) {
    if (err instanceof BudgetExhaustedError) {
      return new Response(
        JSON.stringify({ error: "upstream_limit", message: err.message }),
        { status: 503, headers: { "Content-Type": "application/json" } }
      );
    }
    throw err;
  }
}
```

## Anti-patterns

- Using `fetch()` inside a `while` loop with a dynamic exit condition — a misconfigured condition exhausts the subrequest budget without any compile-time signal.
- Treating KV, D1, and R2 calls as "free" and only counting outbound `fetch()` calls in budget tracking — all platform primitives consume subrequest quota.
- Retrying failed subrequests inside the same Worker invocation without decrementing from a shared budget counter — exponential backoff with 3 retries can triple the actual subrequest count.
- Setting the budget limit to exactly 1000 without a safety buffer — error-handling paths (logging, metric emission) also consume subrequests and will fail silently at the hard cap.

## Gotchas

- Durable Object stub `.fetch()` calls count as subrequests from the calling Worker, and the DO itself has its own independent 1000-subrequest budget for calls it makes.
- The `cache.default.match()` and `cache.default.put()` Cache API calls do NOT count as subrequests — they are free relative to the subrequest budget.
- Workers Queues `send()` calls DO consume subrequest budget (1 per message sent), which surprises teams that use queues as a high-volume side-channel for metrics.
- On the Free plan the limit is 50 subrequests, not 1000 — a Worker that passes QA on the Paid plan may break immediately in a free-tier test environment.

## Verification

```bash
# Deploy and exercise the endpoint, inspect headers for budget usage
curl -si https://my-worker.example.com/api/aggregate \
  | grep -E "X-Subrequest-(Used|Remaining)"
# Expected output:
# X-Subrequest-Used: 47
# X-Subrequest-Remaining: 903

# Query METRICS_QUEUE worker logs for high-budget requests (last 1 hour)
wrangler tail metrics-consumer-worker --format json \
  | jq 'select(.logs[].message | contains("subrequest_usage")) | .logs[].message'
```

## Related

- `infra/cloudflare-workers-limits-resource-planning.md`
- `infra/workers-opentelemetry-tail-workers.md`
- `infra/cloudflare-durable-objects-stateful-edge.md`
- `infra/keda-cloudflare-queue-consumers.md`

## Sources

- https://developers.cloudflare.com/workers/platform/limits/#subrequests
- https://developers.cloudflare.com/queues/reference/how-queues-works/
- https://developers.cloudflare.com/workers/runtime-apis/cache/
