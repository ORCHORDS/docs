# Cloudflare Billing Cost Anomaly Detection

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Cloudflare Workers request surge, a D1 read explosion caused by a missing
index, or an R2 egress spike from a misconfigured public bucket can turn a
$50/month bill into a $5,000 bill before the next invoice cycle. Cloudflare
does not natively email you when usage crosses an arbitrary threshold. Teams
discover the problem at month-end, often after the source of the spike has
already been fixed and the evidence is gone.

The goal is a real-time anomaly detector that reads Cloudflare usage metrics
and fires an alert within minutes of a billing-relevant spike — without waiting
for the monthly invoice.

## Context

Cloudflare exposes usage data through two complementary surfaces:

1. **Analytics Engine** — high-resolution custom metrics written by your
   Workers, which you can query via the Analytics Engine SQL API.
2. **GraphQL Analytics API** — Cloudflare's own telemetry: Workers invocation
   counts, R2 operation counts, D1 row reads, KV operations, Pages build
   minutes, and more. Data is available at one-minute granularity with up to
   three months of history.

The GraphQL API is the primary data source for billing-relevant metrics because
it covers platform-level events your code does not instrument (R2 egress, D1
engine-level reads, KV write amplification from bulk operations).

Cost anomaly detection requires:
- A polling worker (or cron trigger) that reads GraphQL usage every 5–15
  minutes.
- A baseline derived from recent history (rolling 7-day same-hour average).
- A threshold policy (absolute cap or % deviation from baseline).
- An alerting sink (PagerDuty, Slack, email).

## Cloudflare GraphQL Usage Queries

### Workers Invocations

```graphql
query WorkersUsage($accountTag: string!, $start: string!, $end: string!) {
  viewer {
    accounts(filter: { accountTag: $accountTag }) {
      workersInvocationsAdaptive(
        limit: 10000
        filter: { datetime_geq: $start, datetime_leq: $end }
        orderBy: [datetime_ASC]
      ) {
        dimensions {
          datetime
          scriptName
        }
        sum {
          requests
          errors
          subrequests
          duration  # GB-s * 1000
        }
      }
    }
  }
}
```

The `duration` field is in GB-milliseconds. Divide by 1,000,000 to get
GB-seconds. The Workers Unbound pricing formula is:

```
cost = (requests / 1_000_000) * 0.30
     + (duration_GB_s / 400_000) * 1.00
```

### R2 Operations

```graphql
query R2Usage($accountTag: string!, $start: string!, $end: string!) {
  viewer {
    accounts(filter: { accountTag: $accountTag }) {
      r2OperationsAdaptiveGroups(
        limit: 10000
        filter: { datetime_geq: $start, datetime_leq: $end }
      ) {
        dimensions { datetime bucketName actionType }
        sum { requests }
      }
    }
  }
}
```

Class A operations (PUT, COPY, DELETE): $0.0045 / 1,000.
Class B operations (GET, HEAD): $0.00036 / 1,000.

### D1 Read Units

```graphql
query D1Usage($accountTag: string!, $start: string!, $end: string!) {
  viewer {
    accounts(filter: { accountTag: $accountTag }) {
      d1AnalyticsAdaptiveGroups(
        limit: 10000
        filter: { datetime_geq: $start, datetime_leq: $end }
      ) {
        dimensions { datetime databaseId }
        sum { readQueries writeQueries rowsRead rowsWritten }
      }
    }
  }
}
```

Rows read beyond the free tier: $0.001 / million.

## Anomaly Detection Worker

```typescript
// cost-anomaly-detector.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    const now = new Date();
    const windowStart = new Date(now.getTime() - 15 * 60 * 1000); // last 15 min
    const baselineStart = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

    const [current, baseline] = await Promise.all([
      fetchWorkersRequests(env, windowStart.toISOString(), now.toISOString()),
      fetchWorkersRequests(env, baselineStart.toISOString(), windowStart.toISOString()),
    ]);

    const currentRPM = current / 15;
    const baselineRPM = baseline / (7 * 24 * 60);

    const deviation = baselineRPM > 0
      ? (currentRPM - baselineRPM) / baselineRPM
      : 0;

    env.ANALYTICS.writeDataPoint({
      blobs: ["workers_rpm"],
      doubles: [currentRPM, baselineRPM, deviation],
      indexes: ["cost_anomaly"],
    });

    if (deviation > 3.0) {  // 300% above 7-day baseline
      await notifySlack(
        env.SLACK_WEBHOOK,
        `Cost anomaly: Workers requests ${(deviation * 100).toFixed(0)}% above 7-day baseline. ` +
        `Current: ${currentRPM.toFixed(0)} RPM, Baseline: ${baselineRPM.toFixed(0)} RPM`
      );
    }
  },
};

async function fetchWorkersRequests(
  env: Env,
  start: string,
  end: string
): Promise<number> {
  const query = `
    query {
      viewer {
        accounts(filter: { accountTag: "${env.CF_ACCOUNT_TAG}" }) {
          workersInvocationsAdaptive(
            limit: 10000
            filter: { datetime_geq: "${start}", datetime_leq: "${end}" }
          ) { sum { requests } }
        }
      }
    }
  `;

  const res = await fetch("https://api.cloudflare.com/client/v4/graphql", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query }),
  });

  const data = (await res.json()) as any;
  return data.data.viewer.accounts[0]
    .workersInvocationsAdaptive
    .reduce((sum: number, row: any) => sum + (row.sum.requests ?? 0), 0);
}

async function notifySlack(webhookUrl: string, message: string): Promise<void> {
  await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: `[Billing Alert] ${message}` }),
  });
}
```

Deploy with a cron trigger firing every 15 minutes:

```toml
# wrangler.toml
name = "cost-anomaly-detector"
main = "cost-anomaly-detector.ts"

[[triggers.crons]]
crons = ["*/15 * * * *"]

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "billing_anomalies"

[vars]
CF_ACCOUNT_TAG = "your-account-tag"
```

Store `CF_API_TOKEN` and `SLACK_WEBHOOK` as encrypted secrets:

```bash
wrangler secret put CF_API_TOKEN
wrangler secret put SLACK_WEBHOOK
```

## Threshold Policies

Implement three tiers of anomaly detection:

| Policy | Trigger Condition | Action |
|--------|-------------------|--------|
| Soft warning | > 2× baseline | Slack notification |
| Hard alert | > 5× baseline | PagerDuty page |
| Absolute cap | > $500 projected monthly cost | Both + auto-disable |

Projected monthly cost calculation:

```typescript
function projectMonthlyCost(
  currentRPM: number,
  durationGBsPerRequest: number
): number {
  const monthlyRequests = currentRPM * 60 * 24 * 30;
  const monthlyDurationGBs = monthlyRequests * durationGBsPerRequest;
  return (monthlyRequests / 1_000_000) * 0.30
       + (monthlyDurationGBs / 400_000) * 1.00;
}
```

## Per-Script Breakdown

Aggregate to account level for the top-level alert, then break down by script
name to identify the culprit:

```typescript
const byScript = await fetchWorkersByScript(env, windowStart, now);
const top3 = Object.entries(byScript)
  .sort(([, a], [, b]) => b - a)
  .slice(0, 3);
// Include in alert: "Top scripts: api-gateway (45%), auth (30%), images (15%)"
```

This allows immediate identification of the offending Worker without a
separate investigation step.

## Anti-patterns

**Querying the GraphQL API on every request.** That itself generates cost.
Batch queries on a cron schedule (every 5–15 minutes), not per-request.

**Using only monthly invoice data.** By the time the invoice arrives the spike
is over and the data is cold. Real-time GraphQL data is the correct signal.

**Single absolute threshold for all scripts.** A high-traffic script may
normally handle 10 million requests/hour. A cold script handling 1,000
requests/hour may have been compromised if it spikes to 500,000. Use
per-script baselines.

**Ignoring R2 egress.** R2 storage ops are cheap, but egress through Workers
is billed as Workers duration. A public-read bucket with no rate limiting can
generate significant cost. Monitor egress separately.

**Not rate-limiting the anomaly detector itself.** The detector fires a Slack
message every 15 minutes if the anomaly persists. Add a cooldown: only alert
once per anomaly event, not once per polling cycle.

## Gotchas

- **GraphQL API rate limits.** The Analytics GraphQL API is rate-limited per
  account. Polling too frequently (< 1 minute) will return 429. Minimum safe
  polling interval is 5 minutes.
- **Data freshness lag.** GraphQL data has a 1–5 minute lag. Do not compare
  the last 1 minute of data against a baseline expecting real-time accuracy.
  Use 10–15 minute aggregation windows.
- **Free tier includes zero-cost rows.** D1's first 5 million row reads per
  day are free. Subtract this before projecting cost.
- **Account tag vs zone ID.** Workers invocations use `accountTag` in the
  filter, not `zoneTag`. Mixing these returns empty data silently.
- **API token scopes required.** The token must have `Account Analytics: Read`
  and `Workers Scripts: Read` permissions. A narrow token reduces blast radius
  if it leaks.

## Verification

1. Deploy the detector to a staging account with low traffic.
2. Run a load test that generates 10× normal request volume.
3. Confirm the Slack alert fires within 20 minutes (one polling cycle with lag).
4. Verify the per-script breakdown correctly identifies the load-test Worker.
5. Check that the cooldown suppresses duplicate alerts for the remainder of the
   load test window.
6. Review Analytics Engine data to confirm all data points were written.

## Related

- `cloudflare-analytics-engine-custom-metrics.md`
- `cloudflare-workers-analytics.md`
- `cost-monitoring-dashboards.md`
- `observability-cost-control.md`
- `workers-error-alerting-pagerduty-integration.md`

## Sources

- Cloudflare GraphQL Analytics API documentation
- Cloudflare Workers Pricing page (2025)
- Cloudflare R2 Pricing page (2025)
- Cloudflare D1 Pricing page (2025)
- "FinOps at the Edge" — Cloudflare Blog, 2024
