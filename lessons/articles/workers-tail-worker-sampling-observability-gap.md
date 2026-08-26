# Workers Tail Worker Sampling and the Observability Gap at High Traffic

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
During a viral traffic spike, the team's tail worker — responsible for forwarding structured logs to
Logpush and feeding error counts to an alerting dashboard — began dropping events silently. A P0
error surge was missed for 22 minutes because the alert threshold was calibrated against sampled log
volume, which collapsed when the tail worker itself became overloaded and Cloudflare's platform-level
sampling kicked in.

## Context
Tail workers receive a stream of `TraceItem` events from the main Worker and are subject to the same
CPU time and memory limits as any other Worker. Under normal traffic (≤ 5 000 req/s), the tail worker
processed every event synchronously. During the spike (peak 180 000 req/s), Cloudflare's runtime
automatically rate-limits the event stream delivered to the tail worker — a behaviour documented but
not operationally accounted for by the team. Because alert thresholds were set as absolute error counts
per minute rather than error rates (errors / total requests), the drop in sampled events caused the
absolute count to fall below the alert threshold even as the underlying error rate rose sharply.

## Understanding Tail Worker Sampling

Cloudflare does not guarantee that a tail worker receives an event for every main Worker invocation.
At high throughput the platform samples the event stream. The `TraceItem` type exposes a
`truncationReason` field and each item's `event.request` is present only when the event was not
truncated. There is no SDK-level "sample rate" the tail worker can observe directly.

```typescript
// Tail worker — examining sampling signals
export default {
  async tail(events: TraceItem[]): Promise<void> {
    for (const event of events) {
      // events.length < expected_batch_size can be a sign of sampling
      const isTruncated = event.truncationReason !== undefined;
      const outcomeLabel = event.outcome; // "ok" | "exception" | "exceededCpu" | "canceled" | "unknown"

      if (isTruncated) {
        // Log a counter so we know sampling is active — don't try to reconstruct missing data
        console.warn(JSON.stringify({
          event: "tail_event_truncated",
          reason: event.truncationReason,
          outcome: outcomeLabel,
        }));
        continue;
      }

      await forwardToLogpush(event);
    }
  },
};
```

The tail worker has no way to know how many events were dropped between delivery batches.

## Rate-Based Alerting Over Absolute Counts

The core fix was changing all alerting from absolute counts to rate expressions. Workers Analytics
Engine was already receiving a data point per main Worker execution (written inside the main Worker,
not the tail worker, so it is not subject to tail worker sampling):

```typescript
// Main worker — write a data point regardless of tail worker health
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    let outcome: "ok" | "error" = "ok";
    try {
      return await handleRequest(request, env);
    } catch (err) {
      outcome = "error";
      throw err;
    } finally {
      // This executes even when the handler throws
      ctx.waitUntil(
        Promise.resolve().then(() => {
          env.ANALYTICS.writeDataPoint({
            blobs: [request.method, new URL(request.url).pathname, outcome],
            doubles: [1],
            indexes: [outcome],
          });
        }).catch(() => {}) // Never let AE writes crash the main handler
      );
    }
  },
};
```

With raw request and error counts in Analytics Engine (which has its own independent pipeline
from tail workers), the alert query became:

```sql
-- Cloudflare Analytics Engine SQL API
SELECT
  toStartOfInterval(timestamp, INTERVAL '1' MINUTE) AS minute,
  SUM(IF(_blob3 = 'error', _double1, 0)) AS errors,
  SUM(_double1) AS total,
  SUM(IF(_blob3 = 'error', _double1, 0)) / SUM(_double1) AS error_rate
FROM analytics_dataset
WHERE timestamp > NOW() - INTERVAL '10' MINUTE
GROUP BY minute
ORDER BY minute DESC
```

Alert fires when `error_rate > 0.01` (1 %) for 3 consecutive minutes.

## Tail Worker Architecture for Resilience

The tail worker was refactored to be a thin forwarder that writes to a Cloudflare Queue rather than
directly to Logpush, so that back-pressure during spikes queues events rather than dropping them:

```typescript
// Resilient tail worker — queue events, let a consumer handle forwarding
export default {
  async tail(events: TraceItem[], env: Env, ctx: ExecutionContext): Promise<void> {
    const messages = events
      .filter((e) => e.truncationReason === undefined)
      .map((e) => ({ body: serializeTraceItem(e) }));

    if (messages.length === 0) return;

    ctx.waitUntil(
      env.LOG_QUEUE.sendBatch(messages).catch((err) => {
        // Queue send failure — write a minimal counter to AE so we know we lost events
        env.ANALYTICS.writeDataPoint({
          blobs: ["tail_queue_drop"],
          doubles: [messages.length],
          indexes: ["queue_drop"],
        });
      })
    );
  },
};
```

A separate Queue consumer writes batches to Logpush via HTTP at a controlled rate, decoupling
log throughput from the tail worker's CPU budget.

## Capacity Planning for Tail Workers

Tail workers share the same CPU time limits as main Workers (10 ms CPU default on bundled plans).
At 180 000 req/s and a tail worker that does 0.5 ms of CPU per event, the theoretical CPU demand
is 90 000 ms/s — clearly exceeding one Worker instance. The platform spawns additional tail worker
instances but is not obligated to fan out infinitely. Capacity planning must account for this:

```
Max sustainable events/s = (cpu_time_per_event_ms)^-1 * cpu_budget_ms * concurrency_limit
```

For the default plan (10 ms CPU, ~50 concurrent tail worker invocations):
`(0.5)^-1 * 10 * 50 = 1 000 events/s per PoP` — far below the spike rate.

The remedy was both architectural (queue buffering) and operational (upgrading to Workers Unbound
for the tail worker script to get the 30-second CPU budget).

## Anti-patterns
- Alerting on absolute error counts from tail worker logs rather than rates from a sampling-immune
  source (Analytics Engine, D1, or an external metrics system)
- Assuming the tail worker receives 100 % of events at all traffic levels
- Performing expensive I/O (Logpush HTTP call, database writes) synchronously inside the tail worker
  rather than buffering to a Queue
- Sharing a tail worker script between high-traffic and low-traffic routes without per-route sampling
  configuration

## Gotchas
- Tail workers cannot be attached to themselves — you cannot tail a tail worker
- `TraceItem.logs` contains only `console.*` output from the main Worker; `console.*` inside the
  tail worker goes to `wrangler tail` output but not to a nested tail worker
- The `truncationReason` field was added in a mid-2024 runtime update; older worker compatibility
  dates may not expose it — check `compatibility_date` in `wrangler.toml`
- Tail workers count against your account's total Worker script limit; large teams sometimes
  exhaust this with per-service tail workers

## Verification
1. Use `wrangler tail --format=json` on a staging Worker under artificial load (wrk/k6) and
   confirm `truncationReason` appears on events when throughput exceeds ~5 000 req/s.
2. Deliberately kill the Logpush destination and verify the Queue consumer backlog grows (visible
   in Cloudflare dashboard → Queues → consumer backlog) rather than events being silently dropped.
3. Replay the spike scenario in staging and confirm the rate-based alert fires within 3 minutes
   while the old absolute-count alert would have remained silent.

## Related
- `logpush-r2-backpressure-dropped-observability.md`
- `analytics-engine-data-point-limit-exceeded.md`
- `alert-fatigue-masks-real-outages-2026.md`
- `ai-observability-otel-2026.md`
- `queues-consumer-scaling-backpressure-lesson.md`
- `telemetry-sampling-must-retain-rare-failures.md`

## Sources
- Workers Tail Workers — https://developers.cloudflare.com/workers/observability/logs/tail-workers/
- TraceItem type — https://developers.cloudflare.com/workers/runtime-apis/handlers/tail/
- Cloudflare Analytics Engine SQL API — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Workers Queues — https://developers.cloudflare.com/queues/
