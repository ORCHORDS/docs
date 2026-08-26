# Implementing an Error Boundary Reporter in Cloudflare Workers with Analytics Engine

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Unhandled promise rejections in Cloudflare Workers silently fail unless you actively capture them. Without a structured error boundary, you cannot distinguish transient 5xx spikes from systematic failures, correlate errors with specific routes, or set meaningful alert thresholds. This article shows how to wire a global error boundary that feeds Analytics Engine so you can query and alert on real error rates.

## Context

Cloudflare Workers support `addEventListener('unhandledrejection')` in service-worker format and an equivalent `fetch` handler error catch in module Workers. Analytics Engine provides a time-series write path (`writeDataPoint`) that accepts up to 20 `blobs` (strings) and 20 `doubles` (numbers) per event, queryable via GraphQL. Tail Workers allow sampling a separate sidecar process against live traffic without modifying the producer Worker. Together these primitives compose a zero-latency observability pipeline that stays entirely within the Cloudflare network.

## Error Boundary Setup in a Module Worker

```typescript
// src/index.ts
import type { AnalyticsEngineDataset } from '@cloudflare/workers-types';

export interface Env {
  ERROR_ANALYTICS: AnalyticsEngineDataset;
  ENVIRONMENT: string;
}

// Utility: trim stack to 512 chars to stay within blob limits
function trimStack(stack: string | undefined): string {
  if (!stack) return 'no-stack';
  return stack.length > 512 ? stack.slice(0, 512) + '…' : stack;
}

async function handleRequest(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const url = new URL(request.url);
  try {
    // Your actual business logic here
    const response = await routeRequest(request, env, ctx);
    // Record success sample (1% via Tail Worker — not inline)
    return response;
  } catch (err: unknown) {
    const error = err instanceof Error ? err : new Error(String(err));
    const status = error.message.includes('not found') ? 404 : 500;

    // Write to Analytics Engine — blobs[0..2], doubles[0]
    env.ERROR_ANALYTICS.writeDataPoint({
      blobs: [
        url.pathname,              // blob1: route
        error.message.slice(0, 256), // blob2: message
        trimStack(error.stack),   // blob3: stack
        env.ENVIRONMENT,          // blob4: environment
        request.method,           // blob5: HTTP method
      ],
      doubles: [status],           // double1: HTTP status code
      indexes: [url.pathname],     // index for fast filtering
    });

    return new Response(JSON.stringify({ error: 'Internal Server Error' }), {
      status,
      headers: { 'content-type': 'application/json' },
    });
  }
}

async function routeRequest(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  // Placeholder router
  return new Response('ok');
}

export default { fetch: handleRequest };
```

## Analytics Engine GraphQL Query for Error Rates

Query error rates over the last hour grouped by route:

```graphql
# POST https://api.cloudflare.com/client/v4/graphql
# Authorization: Bearer $CF_API_TOKEN
{
  viewer {
    accounts(filter: { accountTag: "$ACCOUNT_ID" }) {
      workersAnalyticsEngineAdaptiveGroups(
        limit: 100
        filter: {
          datasetName: "error_analytics"
          datetimeHour_geq: "2026-08-24T00:00:00Z"
          datetimeHour_leq: "2026-08-24T01:00:00Z"
        }
        orderBy: [count_DESC]
      ) {
        count
        dimensions {
          blob1   # route / pathname
          blob4   # environment
        }
        avg {
          double1  # average HTTP status
        }
      }
    }
  }
}
```

## Cloudflare Notification Threshold Alert

Set an alert when the error count exceeds 50 in any 5-minute window:

```bash
# Create notification policy via API
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/alerting/v3/policies" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Workers error rate spike",
    "alert_type": "workers_alert",
    "enabled": true,
    "mechanisms": {
      "email": [{"id": "your-destination-id"}]
    },
    "filters": {
      "threshold": ["50"],
      "time_frame": ["5"]
    }
  }'
```

## Tail Worker Sidecar — 100% Error Sampling, 1% Success Sampling

```typescript
// src/tail.ts
export default {
  async tail(events: TraceItem[], env: Env, ctx: ExecutionContext): Promise<void> {
    const writes: Promise<void>[] = [];

    for (const event of events) {
      const hasException = event.exceptions.length > 0;
      // Sample: always send errors, 1% of successes
      const shouldSend = hasException || Math.random() < 0.01;
      if (!shouldSend) continue;

      const status = (event.response?.status ?? 0);
      const isError = hasException || status >= 500;

      env.ERROR_ANALYTICS.writeDataPoint({
        blobs: [
          event.scriptName ?? 'unknown',
          event.exceptions[0]?.message?.slice(0, 256) ?? '',
          event.exceptions[0]?.name ?? '',
          isError ? 'error' : 'success',
        ],
        doubles: [status, event.wallTimeMs ?? 0],
        indexes: [event.scriptName ?? 'unknown'],
      });
    }
  },
} satisfies ExportedHandler<Env>;
```

```toml
# wrangler.toml — attach tail worker
[[tail_consumers]]
service = "my-tail-worker"
```

## Anti-patterns

- **Logging errors inline with `console.error` only** — logs are ephemeral and not queryable; use Analytics Engine for structured retention.
- **Writing the full stack trace without trimming** — `blobs` have a 1 KB limit; untrimmed stacks silently truncate, losing the most relevant frames.
- **Sampling 100% of all events inline** — use the Tail Worker sidecar to avoid adding latency to the hot path.
- **Alerting on raw error count without a baseline** — set rate-based thresholds (errors / total requests) to avoid alert storms during low-traffic windows.

## Gotchas

- `writeDataPoint` is fire-and-forget; it does not throw on failure, so you cannot confirm delivery from within the Worker.
- Analytics Engine data is available in GraphQL with ~1 minute latency; it is not suitable for sub-minute alerting.
- The `indexes` field on `writeDataPoint` accepts only one value and must be a string ≤64 bytes; exceeding this silently drops the index.
- Tail Workers run in a separate isolate and do not share memory with the producer Worker.
- Module-format Workers do not support `addEventListener('unhandledrejection')`; use a top-level try/catch in `fetch` instead.

## Verification

```bash
# 1. Trigger a test error
curl -X GET https://your-worker.example.com/error-test

# 2. Query Analytics Engine for recent errors (replace vars)
curl -X POST https://api.cloudflare.com/client/v4/graphql \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ viewer { accounts(filter:{accountTag:\"$ACCOUNT_ID\"}) { workersAnalyticsEngineAdaptiveGroups(limit:5 filter:{datasetName:\"error_analytics\"}) { count dimensions { blob1 } } } } }"}'

# 3. Confirm Tail Worker is attached
wrangler tail my-producer-worker --format pretty
```

## Related

- `tail-worker-multi-destination-fanout.md`
- `alert-deduplication-workers-kv-pagerduty.md`
- `workers-ai-model-performance-drift-analytics-engine.md`

## Sources

- Cloudflare Analytics Engine docs — https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare Tail Workers — https://developers.cloudflare.com/workers/observability/tail-workers/
- Cloudflare Notifications API — https://developers.cloudflare.com/notifications/
