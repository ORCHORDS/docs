# Tail Workers for Real-Time Error Alerting

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You need real-time Slack or PagerDuty alerts when a Workers error rate spikes or a specific exception type crosses a threshold — without adding latency to production request handlers.

## Context
Cloudflare Tail Workers receive a stream of `TailEvent` objects after every invocation of the producer Worker. They run asynchronously, outside the critical path, and have access to structured event data: outcome, exception details, console logs, request metadata, and timing. A Tail Worker can aggregate error counts in a Durable Object or KV, compare against a threshold, and fire an alert to an external webhook only when the rate exceeds the limit — preventing alert spam while ensuring signal fidelity. Tail Workers count against their own subrequest and CPU budgets, not the producer's.

## Architecture / Setup

`wrangler.toml` for the **producer** Worker — attach the Tail Worker:
```toml
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[tail_consumers]]
service = "tail-alerter"
```

`wrangler.toml` for the **Tail Worker**:
```toml
name = "tail-alerter"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[durable_objects.bindings]]
name = "ERROR_RATE"
class_name = "ErrorRateTracker"

[[migrations]]
tag = "v1"
new_classes = ["ErrorRateTracker"]

[vars]
ALERT_THRESHOLD = "10"         # errors per window
ALERT_WINDOW_SECONDS = "60"
SLACK_WEBHOOK_URL = ""         # set via secret
PAGERDUTY_ROUTING_KEY = ""     # set via secret
```

Secrets:
```bash
wrangler secret put SLACK_WEBHOOK_URL --name tail-alerter
wrangler secret put PAGERDUTY_ROUTING_KEY --name tail-alerter
```

## Tail Worker Handler and Error Filtering

`src/index.ts` in `tail-alerter`:
```typescript
import { ErrorRateTracker } from "./error-rate-tracker";

export { ErrorRateTracker };

interface Env {
  ERROR_RATE: DurableObjectNamespace;
  SLACK_WEBHOOK_URL: string;
  PAGERDUTY_ROUTING_KEY: string;
  ALERT_THRESHOLD: string;
  ALERT_WINDOW_SECONDS: string;
}

export default {
  async tail(events: TraceItem[], env: Env, _ctx: ExecutionContext): Promise<void> {
    for (const event of events) {
      // Only care about failed invocations
      if (event.outcome !== "exception" && event.outcome !== "exceeded-cpu" && event.outcome !== "exceeded-memory") {
        continue;
      }

      const scriptName = event.scriptName ?? "unknown";
      const exceptions = event.exceptions ?? [];
      const firstException = exceptions[0];

      const errorInfo = {
        scriptName,
        outcome: event.outcome,
        exceptionName: firstException?.name ?? "UnknownError",
        exceptionMessage: firstException?.message ?? "",
        requestUrl: event.request?.url ?? "",
        rayId: event.request?.headers?.["cf-ray"] ?? "",
        timestamp: new Date(event.eventTimestamp).toISOString(),
        cpuTimeMs: event.cpuTime,
      };

      // Route to DO for rate aggregation
      const trackerId = env.ERROR_RATE.idFromName(
        `${scriptName}:${errorInfo.exceptionName}`
      );
      const stub = env.ERROR_RATE.get(trackerId);

      const shouldAlert = await stub.recordError(
        parseInt(env.ALERT_THRESHOLD, 10),
        parseInt(env.ALERT_WINDOW_SECONDS, 10)
      );

      if (shouldAlert) {
        await Promise.allSettled([
          sendSlackAlert(env.SLACK_WEBHOOK_URL, errorInfo),
          sendPagerDutyAlert(env.PAGERDUTY_ROUTING_KEY, errorInfo),
        ]);
      }
    }
  },
};
```

## Durable Object: Rate-Windowed Error Counter

`src/error-rate-tracker.ts`:
```typescript
export class ErrorRateTracker {
  private state: DurableObjectState;
  private count: number = 0;
  private windowStart: number = Date.now();
  private alerted: boolean = false;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async recordError(threshold: number, windowSeconds: number): Promise<boolean> {
    const now = Date.now();
    const windowMs = windowSeconds * 1000;

    // Load persistent state on first call
    const stored = await this.state.storage.get<{
      count: number;
      windowStart: number;
      alerted: boolean;
    }>("state");

    if (stored) {
      this.count = stored.count;
      this.windowStart = stored.windowStart;
      this.alerted = stored.alerted;
    }

    // Reset window if expired
    if (now - this.windowStart > windowMs) {
      this.count = 0;
      this.windowStart = now;
      this.alerted = false;
    }

    this.count++;

    const shouldAlert = this.count === threshold && !this.alerted;
    if (shouldAlert) {
      this.alerted = true;
    }

    // Persist updated state
    await this.state.storage.put("state", {
      count: this.count,
      windowStart: this.windowStart,
      alerted: this.alerted,
    });

    return shouldAlert;
  }
}
```

## Alert Delivery Functions

```typescript
// src/alerts.ts
interface ErrorInfo {
  scriptName: string;
  outcome: string;
  exceptionName: string;
  exceptionMessage: string;
  requestUrl: string;
  rayId: string;
  timestamp: string;
  cpuTimeMs: number | undefined;
}

export async function sendSlackAlert(
  webhookUrl: string,
  info: ErrorInfo
): Promise<void> {
  if (!webhookUrl) return;

  await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: `:rotating_light: *Worker Error Rate Threshold Exceeded*`,
      blocks: [
        {
          type: "section",
          fields: [
            { type: "mrkdwn", text: `*Script:*\n${info.scriptName}` },
            { type: "mrkdwn", text: `*Outcome:*\n${info.outcome}` },
            { type: "mrkdwn", text: `*Exception:*\n${info.exceptionName}` },
            { type: "mrkdwn", text: `*Message:*\n${info.exceptionMessage.slice(0, 200)}` },
            { type: "mrkdwn", text: `*Ray ID:*\n${info.rayId}` },
            { type: "mrkdwn", text: `*Time:*\n${info.timestamp}` },
          ],
        },
      ],
    }),
  });
}

export async function sendPagerDutyAlert(
  routingKey: string,
  info: ErrorInfo
): Promise<void> {
  if (!routingKey) return;

  await fetch("https://events.pagerduty.com/v2/enqueue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      routing_key: routingKey,
      event_action: "trigger",
      dedup_key: `${info.scriptName}:${info.exceptionName}`,
      payload: {
        summary: `[${info.scriptName}] ${info.exceptionName}: ${info.exceptionMessage}`.slice(0, 1024),
        severity: "error",
        source: "cloudflare-tail-worker",
        timestamp: info.timestamp,
        custom_details: {
          script: info.scriptName,
          outcome: info.outcome,
          request_url: info.requestUrl,
          ray_id: info.rayId,
          cpu_time_ms: info.cpuTimeMs,
        },
      },
    }),
  });
}
```

## Anti-patterns
- **Sending an alert on every errored event** — a single bug can trigger thousands of events per minute; always gate on a rate/threshold using a DO or KV counter.
- **Blocking the Tail Worker on alert delivery** — use `Promise.allSettled()` so a slow Slack webhook does not delay processing of subsequent events.
- **Logging sensitive request body content in Tail events** — Tail Workers receive whatever console logs the producer emits; avoid logging PII or secrets in the producer.
- **Creating one DO per Ray ID** — partition DOs by `scriptName:exceptionType`, not per-request, or you exhaust DO storage with millions of tiny objects.
- **Using a Tail Worker for general metrics collection** — Analytics Engine + adaptive sampling is better for high-cardinality metrics; Tail Workers shine for exception alerting where low volume is expected.

## Gotchas
- Tail Workers are invoked with a batch of up to 100 `TraceItem` events; iterate the whole array, not just `events[0]`.
- The `event.outcome` field values are: `"ok"`, `"exception"`, `"exceeded-cpu"`, `"exceeded-memory"`, `"canceled"`, `"unknown"` — not HTTP status codes.
- Tail Workers run after the response has been sent; they cannot modify the response or add headers.
- A Tail Worker that itself throws will not retry and will not trigger another Tail Worker (no Tail-of-Tail chaining).
- The `event.request.headers` object in `TraceItem` only includes headers the producer explicitly logged via `console.log` or if tracing is configured — it is not the full HTTP header set.
- PagerDuty `dedup_key` collapses repeated alerts into one incident; use `scriptName:exceptionName` so each distinct error type creates its own incident.

## Verification
```bash
# Trigger a test error in the producer and watch Tail Worker logs
wrangler tail api-worker &
wrangler tail tail-alerter &
curl https://api-worker.example.com/force-error

# Check DO storage to confirm threshold counting
wrangler do get ERROR_RATE "api-worker:TypeError" --name tail-alerter

# Verify Tail Worker is attached
wrangler deployments list --name api-worker | grep tail
```

## Related
- [workers-tail-workers.md](workers-tail-workers.md)
- [durable-objects-alarms.md](durable-objects-alarms.md)
- [durable-objects-rate-limiter-pattern.md](durable-objects-rate-limiter-pattern.md)
- [workers-trace-events-debug-tooling.md](workers-trace-events-debug-tooling.md)
- [cloudflare-workers-analytics-engine-sampling.md](cloudflare-workers-analytics-engine-sampling.md)

## Sources
- https://developers.cloudflare.com/workers/observability/logs/tail-workers/
- https://developers.cloudflare.com/workers/runtime-apis/handlers/tail/
- https://developers.cloudflare.com/durable-objects/api/state/
- https://api.slack.com/messaging/webhooks
- https://developer.pagerduty.com/api-reference/368ae3d938c9e-send-an-event-to-pager-duty
