# Analytics Engine Data Point Budget Exhausted Silenced Metrics for 6 Hours

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

The example project platform's real-time operational dashboard went dark for approximately 6 hours during a high-traffic promotional event. Charts showed flat lines at the last value recorded before the gap. Alerts dependent on Analytics Engine query results stopped firing, creating a blind spot during the highest-revenue window of the quarter. Engineers initially suspected a dashboard rendering bug; the actual cause was that the Cloudflare Analytics Engine write quota for the account had been exhausted by mid-afternoon.

## Context

example project instruments every edge Worker with fine-grained Analytics Engine writes: per-request latency, per-route error rates, cache hit ratios, and per-customer API usage counters. The implementation used a `writeDataPoint()` call on every single HTTP request with no sampling or rate-limiting. During normal traffic this produced approximately 180,000 data points per hour across all Workers. The account was on the Workers Paid plan, which allows up to 25 million Analytics Engine data point writes per day. The promotional campaign drove a 14× traffic spike from a product-hunt listing, pushing write rates to 2.5 million data points per hour — exhausting the daily budget in under 10 hours.

## Timeline

- **08:00 UTC** – Promotional campaign goes live. Traffic begins climbing.
- **09:45 UTC** – Traffic reaches 8× baseline. Analytics Engine writes scale proportionally; no alert exists for write budget.
- **11:22 UTC** – Analytics Engine write quota silently exhausted. `writeDataPoint()` calls begin failing silently — Workers API does not throw on quota exhaustion, it drops writes.
- **11:22–17:30 UTC** – Metrics dashboard shows flat lines. No error surfaces in Worker logs because the AE client does not throw.
- **13:05 UTC** – On-call engineer notices dashboard flatlines but attributes them to a dashboard deployment earlier that morning.
- **14:50 UTC** – Second engineer escalates; Grafana panels dependent on AE SQL API return empty rows for the last 3 hours.
- **15:15 UTC** – Cloudflare dashboard inspected; account analytics show AE writes dropped to zero at 11:22 UTC exactly.
- **15:30 UTC** – Root cause confirmed: daily data point budget exhausted.
- **15:45 UTC** – Emergency fix: sampling rate dropped to 1-in-10 for non-critical metrics; critical error metrics downsampled to 1-in-3. Writes resume.
- **17:30 UTC** – Backfill not possible (AE does not support historical inserts). Gap accepted; post-incident review scheduled.

## Root Cause

Every Worker request wrote an Analytics Engine data point unconditionally. During normal traffic volumes this was within budget, so the pattern was never stress-tested. The promotional traffic spike was not modelled against the AE write budget during capacity planning. Cloudflare Analytics Engine silently drops writes when the account-level daily budget is exceeded — it returns no error to the caller — so the exhaustion was invisible until engineers noticed missing data. No monitoring existed for AE write budget consumption, and the Cloudflare dashboard does not send native alerts when the quota threshold is approached.

## Fix: Probabilistic Sampling and Write Budget Monitoring

The immediate fix was adaptive sampling. Non-critical metrics (cache ratios, latency percentiles for successful requests) are written with a 10% sample rate. Error events and payment-path metrics are written at 100% to preserve full fidelity for incidents. A separate Budget Guard Worker tracks hourly write counts via a Durable Object counter and can dynamically lower the sampling rate if the burn rate projects to exceed the daily quota.

```typescript
// src/observability/analytics-engine.ts

export interface AEWriteOptions {
  /** 0.0–1.0 sampling probability. 1.0 = always write. */
  sampleRate?: number;
}

/**
 * Writes a data point to Analytics Engine with configurable sampling.
 * Silently drops the write if the sample lottery fails.
 */
export function writeMetric(
  ae: AnalyticsEngineDataset,
  payload: AnalyticsEngineDataPoint,
  opts: AEWriteOptions = {}
): void {
  const rate = opts.sampleRate ?? 1.0;
  if (rate < 1.0 && Math.random() > rate) return; // sampled out
  try {
    ae.writeDataPoint(payload);
  } catch {
    // AE client does not currently throw on quota exhaustion,
    // but guard against future SDK behaviour changes.
  }
}

// Usage — request latency (non-critical, sample at 10%):
writeMetric(env.example project_METRICS, {
  blobs: [request.method, new URL(request.url).pathname],
  doubles: [latencyMs],
  indexes: ["request_latency"],
}, { sampleRate: 0.1 });

// Usage — payment error (critical, always write):
writeMetric(env.example project_METRICS, {
  blobs: ["payment_error", errorCode],
  doubles: [1],
  indexes: ["payment_errors"],
}, { sampleRate: 1.0 });
```

To track write budget consumption, a Durable Object maintains a rolling hourly counter and exposes a burn-rate estimate:

```typescript
// src/durable-objects/AEBudgetGuard.ts

export class AEBudgetGuard implements DurableObject {
  private writesThisHour = 0;
  private hourStart = Date.now();
  private readonly HOURLY_BUDGET = 1_041_666; // 25M / 24h

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/increment") {
      const body = await request.json<{ count: number }>();
      this.refreshHourIfNeeded();
      this.writesThisHour += body.count;
      const burnPct = (this.writesThisHour / this.HOURLY_BUDGET) * 100;
      return Response.json({ writesThisHour: this.writesThisHour, burnPct });
    }

    if (url.pathname === "/status") {
      this.refreshHourIfNeeded();
      const burnPct = (this.writesThisHour / this.HOURLY_BUDGET) * 100;
      // Recommend reduced sampling if burning hot
      const recommendedRate = burnPct > 80 ? 0.1 : burnPct > 50 ? 0.3 : 1.0;
      return Response.json({ burnPct, recommendedRate });
    }

    return new Response("Not found", { status: 404 });
  }

  private refreshHourIfNeeded(): void {
    if (Date.now() - this.hourStart > 3_600_000) {
      this.writesThisHour = 0;
      this.hourStart = Date.now();
    }
  }
}
```

A scheduled Cron Worker queries the Budget Guard every 15 minutes and writes the burn-rate to a separate low-volume AE dataset (or to a KV key) so Grafana can alert:

```typescript
// src/scheduled/ae-budget-check.ts
export async function checkAEBudget(env: Env): Promise<void> {
  const id = env.AE_BUDGET_GUARD.idFromName("global");
  const stub = env.AE_BUDGET_GUARD.get(id);
  const resp = await stub.fetch("https://internal/status");
  const { burnPct, recommendedRate } = await resp.json<{
    burnPct: number;
    recommendedRate: number;
  }>();

  // Alert if burning more than 90% of hourly budget
  if (burnPct > 90) {
    await env.example project_METRICS.writeDataPoint({
      blobs: ["ae_budget_critical"],
      doubles: [burnPct],
      indexes: ["ae_burn_rate_alert"],
    });
    // Optionally: push alert to PagerDuty webhook
    await fetch(env.PAGERDUTY_WEBHOOK_URL, {
      method: "POST",
      body: JSON.stringify({
        summary: `AE write budget at ${burnPct.toFixed(1)}% of hourly limit`,
        severity: "critical",
      }),
    });
  }
}
```

## Prevention Checklist

- [ ] Never write an Analytics Engine data point on 100% of requests without modelling peak traffic against the daily write budget.
- [ ] Classify metrics by criticality and assign a sample rate: errors/payments = 100%, latency/cache = 10–20%.
- [ ] Implement a budget guard (DO counter or KV key) that tracks hourly AE write velocity and alerts at 80% consumption.
- [ ] Add a Grafana panel showing AE write budget burn rate; alert if projected daily spend exceeds 90% by noon.
- [ ] Include AE write budget in pre-event capacity planning for campaigns and traffic spikes.

## Monitoring Gaps Identified

- No alert existed for Analytics Engine write quota consumption. The system silently dropped writes with no signal to the application layer.
- The monitoring system itself (AE) was the single point of observability — when AE writes failed, all dashboards depending on AE went blind simultaneously, a monitoring monoculture failure.

## Anti-patterns

- Using Analytics Engine as a high-cardinality per-request log rather than a sampled metrics system.
- Not validating that observability infrastructure can absorb the same traffic spike as the application it monitors.
- Trusting that a "fire and forget" write API will self-throttle; Cloudflare AE drops data silently, it does not backpressure the caller.

## Gotchas

- Analytics Engine `writeDataPoint()` does not return an error or throw when the account quota is exceeded — writes silently disappear. There is no per-request confirmation of successful ingestion.
- The Cloudflare dashboard shows AE usage in the "Analytics" section but does not send native email or webhook alerts when the daily limit is approached; you must build your own budget monitor.
- AE SQL API queries against a dataset that received no writes in the query window return an empty result set, not a quota error — callers must distinguish between "no events happened" and "quota exceeded".

## Verification

```bash
# Query AE to confirm data is flowing (replace dataset and account IDs)
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"query":"SELECT count() FROM example project_metrics WHERE timestamp > NOW() - INTERVAL '\''1'\'' HOUR"}' \
  | jq '.data'

# Check the budget guard Durable Object status via the internal admin endpoint
curl "https://example project-admin.workers.dev/internal/ae-budget/status" \
  -H "Authorization: Bearer $example project_ADMIN_TOKEN" | jq .

# Verify sampling is working (request count / 10 should roughly equal AE write count for sampled paths)
# Compare Worker analytics (total requests) with AE row count over a 5-minute window
```

## Related

- `lessons/alert-fatigue-masks-real-outages-2026.md`
- `lessons/logpush-r2-backpressure-dropped-observability.md`
- `lessons/workers-ai-rate-limit-exceeded-production-incident.md`

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/limits/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/durable-objects/
