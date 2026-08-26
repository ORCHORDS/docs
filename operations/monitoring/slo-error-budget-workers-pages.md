# SLO Definition and Error Budget Tracking —
# Cloudflare Workers + Pages (example project)

Date:   2026-08-22
Author: example.com
Status: active

---

## Symptom

example project engineers receive PagerDuty pages at 3 AM for individual
spike alerts that reset by the time anyone looks. Meanwhile the
mobile error rate has been silently elevated at 2.4 % for six weeks —
never breaching the per-minute alert threshold, but consuming the
entire 30-day error budget. There is no mechanism to detect slow
budget burn before users notice.

---

## Context

Service Level Objectives (SLOs) describe the acceptable reliability
target for a service. An error budget is the tolerance for failure
derived from the SLO: `budget = 1 − SLO_target`. Burn rate alerts
fire when the budget is being consumed faster than it can regenerate,
giving early warning before the full window expires.

example project has distinct SLO targets per device class because mobile
clients exhibit structurally different failure modes: flaky LTE
handoffs, app backgrounding causing mid-request drops, and OS memory
pressure killing tabs. Bundling mobile and desktop into a single
SLO hides the mobile degradation.

---

## SLI Definitions for example project

Service Level Indicators (SLIs) are the measured quantities.

```
SLI: Availability (Workers)
  Good event:  HTTP response status in {1xx, 2xx, 3xx, 4xx*}
  Bad event:   HTTP response status in {5xx} OR request timeout
  (* 4xx are user errors, not service errors — exclude 429 if
     rate-limiting is intentional behaviour)

SLI: Latency (Workers)
  Good event:  Response wall time ≤ 1 000 ms
  Bad event:   Response wall time > 1 000 ms OR no response
  Threshold choice: p95 target, not p50 — protects the tail

SLI: Pages Asset Availability
  Good event:  Cloudflare Pages CDN returns 2xx for asset requests
  Bad event:   5xx or connection error from Pages CDN

SLI: D1 Query Success
  Good event:  D1 query completes within 500 ms
  Bad event:   D1 error OR duration > 500 ms
```

---

## SLO Targets — example project (30-Day Windows)

| Service              | Device  | Availability SLO | Latency SLO  | Budget (30 d)  |
|----------------------|---------|------------------|--------------|----------------|
| example project-api Worker      | Mobile  | 99.5 %           | 95 % ≤ 1 s   | 216 min avail. |
| example project-api Worker      | Desktop | 99.8 %           | 95 % ≤ 500ms | 86.4 min avail.|
| example project-pages Pages     | Mobile  | 99.9 %           | —            | 43.2 min avail.|
| example project-pages Pages     | Desktop | 99.9 %           | —            | 43.2 min avail.|
| D1 (prod-db)         | All     | 99.5 %           | 95 % ≤ 500ms | 216 min query  |

Mobile availability SLO is intentionally 0.3 pp lower than desktop
to account for connection-abort events that are not service faults.

---

## Error Budget Calculation

```
30-day window = 30 × 24 × 60 = 43 200 minutes
                             = 43 200 × (requests/min average)

For mobile availability at 99.5 % SLO:
  Budget fraction = 1 − 0.995 = 0.005
  Budget minutes  = 43 200 × 0.005 = 216 minutes of downtime
  Budget requests = total_mobile_requests × 0.005

If daily mobile traffic = 10 M requests:
  30-day budget = 300 M × 0.005 = 1 500 000 bad events
  Remaining budget after week 1 = budget − actual_bad_events_week_1
```

---

## Burn Rate Alerts — Multi-Window Model

A burn rate of 1× means the budget is consumed at exactly the rate
that would exhaust it by end of window. Google SRE recommend a
2-window approach: a short window catches fast burns; a long window
catches slow burns.

| Alert name             | Short window | Long window | Burn rate | Severity |
|------------------------|-------------|-------------|-----------|----------|
| Critical mobile burn   | 1 h         | 5 min       | 14.4×     | page     |
| High mobile burn       | 6 h         | 30 min      | 6×        | ticket   |
| Warning mobile burn    | 3 d         | 6 h         | 1×        | slack    |

Burn rate 14.4× means the budget will be exhausted in 30/14.4 ≈ 2
days at the current rate. The 5-minute confirmation window prevents
false positives from spikes.

---

## Analytics Engine Queries for SLO Tracking

example project emits one Analytics Engine data point per Worker invocation.

Write schema (from the Worker):

```typescript
env.AE_DATASET.writeDataPoint({
  blobs:   [
    request.cf?.deviceType ?? "unknown",  // blob1: device
    request.cf?.country    ?? "XX",        // blob2: country
    String(response.status),               // blob3: status
    env.ENVIRONMENT,                        // blob4: env
  ],
  doubles: [
    wallMs,      // double1: wall time ms
    cpuMs,       // double2: cpu time ms
    d1QueryMs,   // double3: D1 total ms
  ],
  indexes: [
    request.cf?.colo ?? "???",             // index1: PoP colo
  ],
});
```

Query — 30-day mobile availability SLO:

```sql
SELECT
  SUM(CASE WHEN CAST(blob3 AS INTEGER) >= 500 THEN 1 ELSE 0 END)
    AS bad_events,
  COUNT(*) AS total_events,
  1 - (bad_events * 1.0 / total_events) AS availability,
  (bad_events * 1.0 / total_events) / 0.005 AS burn_rate
FROM example project_metrics
WHERE timestamp >= NOW() - INTERVAL '30' DAY
  AND blob1 = 'mobile'
  AND blob4 = 'production';
```

Query — hourly burn rate (for fast-burn alert):

```sql
SELECT
  toStartOfHour(timestamp) AS hour,
  COUNT(*)                  AS total,
  SUM(CASE WHEN CAST(blob3 AS INTEGER) >= 500 THEN 1 ELSE 0 END)
                            AS bad,
  bad * 1.0 / total / 0.005 AS burn_rate_1h
FROM example project_metrics
WHERE timestamp >= NOW() - INTERVAL '6' HOUR
  AND blob1 = 'mobile'
GROUP BY hour
ORDER BY hour;
```

---

## Mobile-Specific Error Rate Adjustments

Mobile clients exhibit failure modes that inflate the SLI error count
without reflecting a service defect:

| Event type                    | Appears as           | Adjustment                      |
|-------------------------------|----------------------|---------------------------------|
| App backgrounded mid-request  | TCP RST / 499        | Exclude 499-class from bad count|
| LTE handoff (20–200 ms gap)   | Timeout if < 100 ms  | Use 2 s timeout threshold       |
| OS kill (low memory)          | No response received | Client-side metric only         |
| Captive portal redirect       | 302 to login page    | Exclude 302 from bad events     |

The Workers runtime does not natively emit 499 (client disconnect)
as a status code in Logpush — the `Outcome` field shows `canceled`
instead of `error`. Filter on `Outcome != canceled` before counting
bad events.

```javascript
// In the Analytics Engine writeDataPoint call:
const outcome = response.status >= 500
  ? "error"
  : wasClientDisconnect   // detect via AbortSignal
    ? "canceled"
    : "ok";
// Only write "error" outcomes to the bad-event counter
```

---

## Anti-Patterns

- Using a single SLO across mobile and desktop. Mobile p99 latency
  being 4× desktop is not a bug — it is structural. A shared SLO
  either page-storms on mobile or hides desktop regressions.
- Setting a 99.99 % SLO for a Workers-based API without Workers
  Paid plan. Free plan Workers have no SLA from Cloudflare and the
  upstream SLO is vacuous.
- Alerting on raw error rate with no burn rate window. A 10-minute
  spike to 5 % error rate does not breach a 99.5 % 30-day SLO.
- Counting D1 `canceled` outcomes from client disconnects as bad
  events. This inflates the apparent error rate by 15–25 % on mobile.

---

## Gotchas

- Analytics Engine has a 5-minute ingestion delay. Do not use it for
  real-time alerting under a 5-minute resolution.
- Analytics Engine data points have a hard limit of 20 blobs, 20
  doubles, and 1 index per write call. Exceeding this silently drops
  the extra fields.
- The Analytics Engine SQL API is available only on the Workers Paid
  plan ($5/month minimum). On Free plans, use Logpush to R2 + DuckDB
  for SLO queries.
- Burn rate alerts require a stable baseline request rate. During
  traffic growth phases the budget denominator (total requests)
  grows, making fixed-request budgets automatically more lenient.
  Recalculate budgets quarterly or tie them to a percentage, not an
  absolute count.

---

## Verification

```bash
# Check current error budget remaining (last 30 days, mobile)
curl "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT COUNT(*) as total, SUM(CASE WHEN blob3 >= '\''500'\'' THEN 1 ELSE 0 END) as bad FROM example project_metrics WHERE timestamp >= NOW() - INTERVAL '\''30'\'' DAY AND blob1 = '\''mobile'\'' AND blob4 = '\''production'\''"}' \
  | jq '.data[0] | {total: .total, bad: .bad, remaining_budget_pct: (((.total * 0.005) - .bad) / (.total * 0.005) * 100)}'

# Confirm Logpush job is running
curl "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/logpush/jobs" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '[.result[] | select(.enabled) | .name]'
```

---

## Related

- documentation/categories/monitoring/slo-error-budgets-burn-rate-alerting.md
- documentation/categories/monitoring/multiwindow-burn-rate-slo-alerts.md
- documentation/categories/monitoring/error-budget-policy.md
- documentation/categories/monitoring/cloudflare-analytics-engine-custom-metrics.md
- documentation/categories/monitoring/rum-mobile-desktop-cwv-disparity.md

---

## Source URLs

- https://sre.google/workbook/alerting-on-slos/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/workers/observability/metrics/
- https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/
- https://developers.cloudflare.com/logs/reference/log-fields/zone/workers_trace_events/
