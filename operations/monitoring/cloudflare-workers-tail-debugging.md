# Cloudflare Tail Workers — Real-Time Request Debugging

Date:   2026-08-22
Author: example.com
Status: active

---

## Symptom

Mobile traffic shows elevated error rates in Cloudflare Analytics but
the exact request shapes causing failures are invisible. Standard
`wrangler tail` in CI does not capture production headers such as
`Sec-CH-UA-Mobile` or `User-Agent` detail needed to distinguish phone
clients from desktop browsers. Engineers need live request inspection
without deploying a debug build.

---

## Context

Tail Workers are a Cloudflare-native mechanism: a second Worker
receives a copy of every invocation event (request, response, logs,
exceptions) from a target Worker in near-real time. Unlike
`wrangler tail`, Tail Workers persist as a deployed resource, cost
nothing per non-invocation, and can be filtered, enriched, and
forwarded to any sink.

example project routes ~70 % of traffic from mobile clients. The
mobile-vs-desktop error split is the primary SLO concern. Tail
Workers are the fastest way to achieve per-device-class visibility
without modifying the hot path.

---

## Wrangler Tail — Fast Local Inspection

`wrangler tail` streams events from a running Worker to stdout.
Useful for short debugging sessions; not suitable for sustained
production observation.

```bash
# Stream all events from the example project API Worker
wrangler tail example project-api --format pretty

# Filter to mobile requests by matching header value
wrangler tail example project-api \
  --format pretty \
  --search "Sec-CH-UA-Mobile: ?1"

# Filter to 5xx responses only
wrangler tail example project-api \
  --format pretty \
  --status error
```

Flags available as of Wrangler 3:

```
--format      pretty | json
--search      substring match on full event JSON
--status      ok | error | canceled
--ip          client IP allowlist (comma-separated)
--header      "Name: Value" match
--method      GET | POST | …
--sampling-rate  0.0–1.0  (default 1.0)
```

Note: `--search` is case-sensitive and matches on the serialised
event JSON, so searching `"mobile"` also matches URLs containing
the word "mobile".

---

## Tail Worker Architecture

```
 ┌───────────────────┐   invocation event   ┌────────────────┐
 │  example project-api Worker  │ ──────────────────►  │  example project-tail     │
 │  (producer)       │                      │  Worker        │
 └───────────────────┘                      └───────┬────────┘
                                                    │
                          ┌─────────────────────────┤
                          │                         │
                    ┌─────▼──────┐          ┌───────▼──────┐
                    │  R2 bucket │          │  Analytics   │
                    │  (raw log) │          │  Engine      │
                    └────────────┘          └──────────────┘
```

`wrangler.toml` binding for the tail consumer:

```toml
# example project-api/wrangler.toml
[tail_consumers]
service = "example project-tail"
```

```toml
# example project-tail/wrangler.toml
name = "example project-tail"
main = "src/index.ts"
compatibility_date = "2025-11-01"
```

---

## Mobile vs Desktop Request Signature Differences

Cloudflare populates the `cf` object on every request. In a Tail
Worker the event contains the original `request` including headers.

| Signal                    | Mobile value          | Desktop value        |
|---------------------------|-----------------------|----------------------|
| `Sec-CH-UA-Mobile`        | `?1`                  | `?0`                 |
| `cf.deviceType`           | `mobile`              | `desktop`            |
| `User-Agent`              | contains `Mobile`     | rarely               |
| `cf.screenWidth`          | ≤ 480 (typical)       | ≥ 1024 (typical)     |
| `Accept` image preference | `image/avif,image/webp` | same (order varies)|
| `connection` close rate   | higher (LTE switch)   | lower                |

Tail Worker filtering by device class:

```typescript
export default {
  async tail(events: TraceItem[]): Promise<void> {
    for (const event of events) {
      const req   = event.event?.request;
      const isMob = req?.headers?.["sec-ch-ua-mobile"] === "?1"
                 || event.event?.cf?.deviceType === "mobile";

      const record = {
        ts:      event.eventTimestamp,
        device:  isMob ? "mobile" : "desktop",
        status:  event.event?.response?.status,
        url:     req?.url,
        ray:     req?.headers?.["cf-ray"],
        ms:      event.wallTimeMs,
      };

      // only forward failures
      if (record.status && record.status >= 500) {
        await forwardToSink(record);
      }
    }
  },
};
```

---

## Sampling Strategies for High-Volume Mobile Traffic

Tail Workers receive 100 % of events by default. At scale this
becomes expensive to process and store. Apply sampling at the
consumer, not at the producer.

```typescript
const MOBILE_SAMPLE = 0.10;   // 10 % of mobile events
const DESKTOP_SAMPLE = 0.50;  // 50 % of desktop events

function shouldKeep(isMobile: boolean): boolean {
  return Math.random() < (isMobile ? MOBILE_SAMPLE : DESKTOP_SAMPLE);
}
```

Always keep 100 % of error events regardless of sample rate — the
sample gate should only apply to successful requests.

---

## Anti-Patterns

- Logging full request bodies in the Tail Worker. Bodies are not
  available in tail events; attempting to read them returns undefined
  and wastes compute time.
- Using `wrangler tail` as a substitute for a deployed Tail Worker in
  production. `wrangler tail` drops events when your laptop's
  connection is interrupted.
- Emitting one Analytics Engine data point per event without
  aggregating first. At 10 M mobile req/day this hits the AE write
  limit (~25 M writes/day per account on paid plans).
- Routing Tail Worker output back to the same Worker that produces
  the events — creates feedback loops and unbounded invocations.

---

## Gotchas

- Tail Workers have a 1 000 ms CPU time limit per invocation, not
  the same as the producing Worker. Heavy JSON parsing of large
  batches can breach this.
- `cf.deviceType` is set by Cloudflare's device-detection heuristic
  and can mis-classify cheap Android tablets as "desktop."
- The `events` array batches up to 100 invocations per Tail Worker
  call — do not assume one event per call.
- `wrangler tail --search` is AND-joined across multiple flags but
  OR-joined within the same flag type.

---

## Verification

```bash
# Confirm tail consumer binding is deployed
wrangler deployments list --name example project-tail

# Send a synthetic mobile request and watch the tail
curl -H "Sec-CH-UA-Mobile: ?1" https://api.example project.example.com/ping &
wrangler tail example project-tail --format json | jq '.event.request.headers'

# Confirm no tail Worker CPU budget overruns in last 24 h
wrangler tail example project-tail --status error --format json | \
  jq 'select(.exceptions[].name == "Error")'
```

---

## Related

- documentation/categories/monitoring/workers-logpush-observability-pipeline.md
- documentation/categories/monitoring/distributed-tracing-workers-d1-requests.md
- documentation/categories/monitoring/cloudflare-analytics-engine.md
- documentation/categories/monitoring/workers-tail-worker-pii-minimization-and-otel-decision.md
- documentation/categories/monitoring/log-sampling-strategies.md

---

## Source URLs

- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/workers/wrangler/commands/#tail
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://developers.cloudflare.com/analytics/analytics-engine/
