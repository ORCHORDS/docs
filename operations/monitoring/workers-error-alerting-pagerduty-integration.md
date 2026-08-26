# Workers Error Alerting PagerDuty Integration

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Production Workers errors surface in Cloudflare dashboard logs but
do not trigger on-call notifications. The team needs P1/P2 severity
routing to PagerDuty based on error rate, error type, and mobile vs
desktop origin. A mobile error rate spike should page the mobile
squad immediately; a low-rate server error should create a low-
urgency ticket without waking anyone at night.

## Context

Cloudflare Tail Workers receive a stream of `TraceItem` events for
every completed Worker invocation. Each event carries status codes,
exception messages, CPU time, and request metadata. A Tail Worker
can sample these events, aggregate counts in a Durable Object, and
flush to PagerDuty Events API v2 when thresholds are breached.
example project (example.com) routes mobile errors to the `mobile-oncall` policy
and desktop/API errors to `platform-oncall`. PagerDuty Events API v2
accepts either `trigger`, `acknowledge`, or `resolve` events.

## Tail Worker setup

```toml
# wrangler.toml (error-alerter Worker)
name = "example project-error-alerter"
main = "src/tail.ts"
compatibility_date = "2026-06-01"

[[tail_consumers]]
service = "example project-api"      # primary Worker being tailed

[[durable_objects.bindings]]
name = "ERROR_COUNTER"
class_name = "ErrorCounter"

[vars]
PD_ROUTING_KEY_MOBILE   = ""   # set via wrangler secret
PD_ROUTING_KEY_PLATFORM = ""

[[migrations]]
tag = "v1"
new_classes = ["ErrorCounter"]
```

```typescript
// src/tail.ts
export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      const isMobile = isMobileRequest(event);
      const isError  = event.exceptions.length > 0 ||
                       (event.response?.status ?? 0) >= 500;

      if (!isError) continue;

      const key    = isMobile ? 'mobile' : 'platform';
      const doId   = env.ERROR_COUNTER.idFromName(key);
      const stub   = env.ERROR_COUNTER.get(doId);
      await stub.fetch('http://internal/increment', {
        method: 'POST',
        body: JSON.stringify({
          key,
          exception: event.exceptions[0]?.message ?? 'status-5xx',
          status:    event.response?.status ?? 0,
        }),
      });
    }
  },
};

function isMobileRequest(event: TraceItem): boolean {
  const ua = event.request?.headers?.find(
    ([k]) => k.toLowerCase() === 'user-agent',
  )?.[1] ?? '';
  return /mobile|android|iphone|ipad/i.test(ua);
}
```

## Durable Object error aggregator

```typescript
// src/counter.ts
export class ErrorCounter implements DurableObject {
  private errors = 0;
  private lastFlushAt = 0;
  private readonly WINDOW_MS = 60_000;   // 1-minute window
  private readonly THRESHOLD = 10;       // errors per window

  async fetch(request: Request): Promise<Response> {
    const { key, exception, status } = await request.json();
    this.errors++;

    const now = Date.now();
    if (
      this.errors >= this.THRESHOLD &&
      now - this.lastFlushAt > this.WINDOW_MS
    ) {
      await this.triggerPagerDuty(key, exception, status);
      this.lastFlushAt = now;
      this.errors = 0;
    }
    return new Response('ok');
  }

  private async triggerPagerDuty(
    key: string,
    exception: string,
    status: number,
  ): Promise<void> {
    const routingKey = key === 'mobile'
      ? (this.env as Env).PD_ROUTING_KEY_MOBILE
      : (this.env as Env).PD_ROUTING_KEY_PLATFORM;

    await fetch('https://events.pagerduty.com/v2/enqueue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        routing_key:  routingKey,
        event_action: 'trigger',
        dedup_key:    `example project-${key}-errors`,
        payload: {
          summary:   `example project ${key} errors: ${this.errors} in 1 min`,
          source:    'example project-tail-worker',
          severity:  key === 'mobile' ? 'critical' : 'error',
          custom_details: {
            window_errors: this.errors,
            last_exception: exception,
            last_status:    status,
            segment:        key,
          },
        },
      }),
    });
  }
}
```

## PagerDuty Events API v2 severity routing

| Worker segment | Error threshold | PD severity  | PD policy          | Urgency   |
|----------------|----------------|--------------|--------------------|-----------|
| `mobile`       | 10 / 1 min     | `critical`   | `mobile-oncall`    | high      |
| `platform`     | 25 / 1 min     | `error`      | `platform-oncall`  | high      |
| `platform`     | 5–24 / 1 min   | `warning`    | `platform-oncall`  | low       |
| any            | < 5 / 1 min    | —            | no alert           | —         |

PagerDuty deduplication uses `dedup_key`. A second `trigger` with
the same key updates the incident rather than opening a new one.
Send a `resolve` event when the error rate drops below the threshold
for two consecutive windows.

```typescript
// resolve when rate clears
await fetch('https://events.pagerduty.com/v2/enqueue', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    routing_key:  routingKey,
    event_action: 'resolve',
    dedup_key:    `example project-${key}-errors`,
    payload: {
      summary:  `example project ${key} error rate cleared`,
      source:   'example project-tail-worker',
      severity: 'info',
    },
  }),
});
```

## Mobile error rate spike alert logic

A spike is defined as: mobile errors >= 10 within any rolling 60 s
window AND mobile error rate > 5% of mobile requests in the same
window. The second condition requires a request counter alongside
the error counter to avoid false positives during low-traffic
nights when a single error can look like a 100% error rate.

```typescript
// Inside ErrorCounter.fetch — track totals alongside errors
if (key === 'mobile') {
  this.mobileTotal++;
  if (isError) this.mobileErrors++;
}

const mobileErrRate = this.mobileTotal > 0
  ? this.mobileErrors / this.mobileTotal
  : 0;

const shouldAlert =
  this.mobileErrors >= THRESHOLD && mobileErrRate > 0.05;
```

| Condition                         | Fires alert? | Rationale                           |
|-----------------------------------|-------------|-------------------------------------|
| 15 errors, 100 requests (15%)     | Yes         | Above count and rate threshold      |
| 10 errors, 300 requests (3.3%)    | No          | Rate below 5% floor                 |
| 10 errors, 10 requests (100%)     | Yes         | Count met; rate above floor         |
| 3 errors, 50 requests (6%)        | No          | Count below 10-error threshold      |

## Anti-patterns

- **Alerting from every Tail Worker invocation individually** —
  Tail Workers run once per matched invocation; without a Durable
  Object aggregator, each event triggers a PagerDuty API call,
  causing rate-limit errors (PD Events API: 10 k/min per key).
- **Using a single PD routing key for all segments** — mobile and
  platform teams have different on-call schedules; a single policy
  sends every alert to both squads.
- **Setting thresholds in plain numbers without a rate floor** —
  a single error at 3 am during low traffic fires a P1; add the
  rate denominator guard.
- **Not sending `resolve` events** — PagerDuty incidents remain
  open indefinitely, causing alert fatigue and missed new incidents
  buried under open ones.

## Gotchas

- Tail Workers cannot access KV or D1 directly in the current
  runtime; use a Durable Object for stateful accumulation.
- `event.exceptions` is only populated when an uncaught exception
  occurred; a Worker that returns `status: 500` via `new Response`
  will have `exceptions: []` — check `event.response.status` too.
- PagerDuty Events API v2 `dedup_key` is limited to 255 characters;
  keep keys short and deterministic.
- Durable Objects are single-threaded; the aggregation window resets
  on DO eviction (roughly every 30 s of inactivity). Set alarms via
  `this.state.storage.setAlarm()` to keep the DO alive across the
  window.
- The PD Events API v2 endpoint is `events.pagerduty.com`, not the
  REST API at `api.pagerduty.com`; token scopes differ.

## Verification

- Deploy Tail Worker to staging; inject 12 forced 500 responses;
  confirm a PagerDuty incident opens within 90 s on `mobile-oncall`.
- Inject 12 errors spread over 3 minutes (4/min); confirm no alert
  fires (below per-window threshold).
- Inject 12 errors in 1 min then stop; confirm PagerDuty `resolve`
  event is received within 2 min of rate clearing.
- Verify Durable Object alarm is registered: `wrangler tail
  example project-error-alerter --format pretty` should show alarm logs every
  60 s even with zero traffic.
- Confirm `dedup_key` deduplication: two back-to-back threshold
  breaches in the same window produce one incident update, not two.

## Related

- `documentation/categories/monitoring/cloudflare-workers-tail-debugging.md`
- `documentation/categories/monitoring/pagerduty-integration.md`
- `documentation/categories/monitoring/alert-severity-levels.md`
- `documentation/categories/monitoring/escalation-policy-design.md`
- `documentation/categories/monitoring/mobile-crash-monitoring.md`
- `documentation/categories/monitoring/alerting-strategy-routing-escalation.md`

## Sources

- Cloudflare Tail Workers —
  https://developers.cloudflare.com/workers/observability/tail-workers/
- PagerDuty Events API v2 —
  https://developer.pagerduty.com/docs/ZG9jOjExMDI5NTgw-events-api-v2-overview
- PagerDuty dedup key reference —
  https://developer.pagerduty.com/docs/ZG9jOjExMDI5NTgx-pdces-event-dedup
- Cloudflare Durable Objects alarms —
  https://developers.cloudflare.com/durable-objects/api/alarms/
- Workers TraceItem type reference —
  https://developers.cloudflare.com/workers/runtime-apis/tail-event/
