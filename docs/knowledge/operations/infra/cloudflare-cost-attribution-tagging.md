# Cloudflare Cost Attribution and Usage Tagging

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Cloudflare bill arrives as a single line item per product (Workers, R2, D1, KV,
Images, Stream, etc.) with no breakdown by team, product area, or application. When
multiple teams share one Cloudflare account — a common pattern for Workers-centric
stacks — you cannot determine which Worker is driving CPU costs, which R2 bucket is
consuming egress, or which KV namespace is racking up write operations.

Without usage attribution, FinOps conversations stall: engineering management cannot
chargeback costs to the right team, anomalous spend growth is invisible until the monthly
invoice, and capacity-planning decisions rest on guesswork. This article covers
Cloudflare-specific patterns for granular cost attribution and usage tracking.

## Context

Unlike AWS (which has cost allocation tags on virtually every resource) or GCP (which has
billing labels), Cloudflare's billing model is product-centric and does not support
arbitrary tags that flow through to the invoice. Attribution must be constructed by the
operator using:

1. **GraphQL Analytics API** — raw usage counters per Worker script name, R2 bucket,
   D1 database, and KV namespace, queryable by time window.
2. **Analytics Engine** — a write-your-own-metrics store inside Workers; emit cost-proxy
   metrics (request count, CPU ms, byte count) with team/service labels.
3. **Workers Logpush / Tail Workers** — stream structured logs that include script name
   and outcome; aggregate externally.
4. **Account structure** — use separate Cloudflare accounts per business unit; Cloudflare
   supports multi-account management via the dashboard and API.

## Cloudflare account topology for attribution

| Model                     | Isolation  | Attribution | Operational overhead |
|---------------------------|------------|-------------|----------------------|
| Single account, all teams | None       | Manual only | Low                  |
| Sub-accounts per team     | Full       | Invoice-level | High               |
| Single account + naming   | Logical    | GraphQL     | Medium               |

**Recommended for mid-size orgs**: one account, enforce naming conventions, query
GraphQL for per-resource usage. Move to sub-accounts only when chargeback must appear
on separate invoices.

### Naming convention for attribution

Encode `team` and `service` into resource names:

| Resource        | Convention                          | Example                     |
|-----------------|-------------------------------------|-----------------------------|
| Worker          | `{team}-{service}-{env}`            | `platform-api-production`   |
| R2 bucket       | `{team}-{service}-{env}`            | `platform-assets-production`|
| D1 database     | `{team}-{service}-{env}`            | `platform-db-production`    |
| KV namespace    | `{team}-{service}-{env}`            | `platform-sessions-prod`    |
| Queue           | `{team}-{service}-{env}`            | `platform-jobs-production`  |

With this convention, all GraphQL queries can group by prefix string matching.

## GraphQL Analytics API — querying usage

Cloudflare exposes per-Worker, per-R2, per-D1, and per-KV usage via GraphQL at
`https://api.cloudflare.com/client/v4/graphql`.

### Workers usage per script

```graphql
query WorkersUsage($accountTag: String!, $from: Time!, $to: Time!) {
  viewer {
    accounts(filter: { accountTag: $accountTag }) {
      workersInvocationsAdaptive(
        limit: 100
        filter: { datetimeHour_geq: $from, datetimeHour_leq: $to }
        orderBy: [sum_requests_DESC]
      ) {
        sum {
          requests
          errors
          subrequests
        }
        quantiles {
          cpuTimeP50
          cpuTimeP99
        }
        dimensions {
          scriptName
          status
        }
      }
    }
  }
}
```

```bash
# Example — last 7 days
FROM=$(date -u -d "7 days ago" +%Y-%m-%dT%H:%M:%SZ)
TO=$(date -u +%Y-%m-%dT%H:%M:%SZ)

curl -s -X POST https://api.cloudflare.com/client/v4/graphql \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"$(cat workers-usage.graphql)\", \"variables\": {\"accountTag\":\"$ACCOUNT_ID\",\"from\":\"$FROM\",\"to\":\"$TO\"}}" \
  | jq '[.data.viewer.accounts[0].workersInvocationsAdaptive[] | {script: .dimensions.scriptName, requests: .sum.requests, cpuP99: .quantiles.cpuTimeP99}]'
```

### R2 usage per bucket

```graphql
query R2Usage($accountTag: String!, $from: Date!, $to: Date!) {
  viewer {
    accounts(filter: { accountTag: $accountTag }) {
      r2StorageAdaptiveGroups(
        limit: 100
        filter: { date_geq: $from, date_leq: $to }
        orderBy: [sum_payloadSize_DESC]
      ) {
        sum {
          payloadSize
          objectCount
          uploadCount
          deleteCount
        }
        dimensions { bucketName actionType }
      }
    }
  }
}
```

### D1 usage per database

```graphql
query D1Usage($accountTag: String!, $from: Date!, $to: Date!) {
  viewer {
    accounts(filter: { accountTag: $accountTag }) {
      d1AnalyticsAdaptiveGroups(
        limit: 100
        filter: { date_geq: $from, date_leq: $to }
        orderBy: [sum_rowsRead_DESC]
      ) {
        sum { rowsRead rowsWritten }
        dimensions { databaseId }
      }
    }
  }
}
```

D1 billing is based on rows read/written, not query count. A single SELECT with a full
table scan costs more than 100 small indexed lookups.

## Analytics Engine for self-reported cost metrics

When you need sub-Worker attribution (e.g., which API route within one Worker drives
cost), use Analytics Engine to emit custom cost-proxy metrics from the Worker itself:

```typescript
// src/index.ts
export interface Env {
  COST_METRICS: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    const url   = new URL(request.url);
    const route = url.pathname.split("/")[1] ?? "root";

    try {
      const response = await handleRequest(request, env, ctx);
      const cpuMs    = Date.now() - start;

      ctx.waitUntil(
        Promise.resolve(
          env.COST_METRICS.writeDataPoint({
            blobs:   ["success", route, "production"],
            doubles: [cpuMs, response.headers.get("content-length") ? +response.headers.get("content-length")! : 0],
            indexes: [route],
          })
        )
      );

      return response;
    } catch (err) {
      env.COST_METRICS.writeDataPoint({
        blobs:   ["error", route, "production"],
        doubles: [Date.now() - start, 0],
        indexes: [route],
      });
      throw err;
    }
  },
};
```

Query route-level cost proxies:

```graphql
{
  viewer {
    accounts(filter: { accountTag: $accountTag }) {
      workersAnalyticsEngineAdaptiveGroups(
        limit: 100
        filter: { datetimeHour_geq: "2026-08-22T00:00:00Z" }
        orderBy: [sum_double1_DESC]
      ) {
        sum { double1 }     # total CPU ms by route
        count               # total requests
        dimensions { blob1 blob2 }  # outcome, route
      }
    }
  }
}
```

## Cost estimation model

Use these unit prices (as of mid-2026, Workers Paid plan) to build an internal
chargeback model from usage data:

| Resource                  | Pricing unit                     | Approx cost         |
|---------------------------|----------------------------------|---------------------|
| Workers requests          | per 1M requests                  | $0.30               |
| Workers CPU time          | per 1M GB-seconds (on Paid plan) | $0.02               |
| R2 Class A ops            | per 1M (PUT, COPY, POST, LIST)   | $4.50               |
| R2 Class B ops            | per 1M (GET, HEAD)               | $0.36               |
| R2 storage                | per GB-month                     | $0.015              |
| R2 egress                 | Free (no egress fee to internet) | $0.00               |
| D1 rows read              | per 1B rows                      | $0.001              |
| D1 rows written           | per 1M rows                      | $1.00               |
| D1 storage                | per GB-month (beyond free tier)  | $0.75               |
| KV reads                  | per 1M reads                     | $0.50               |
| KV writes                 | per 1M writes                    | $5.00               |

Build a weekly Slack report by combining GraphQL query results with these prices:

```python
# scripts/cost-report.py
import requests, os, json

ACCOUNT_ID = os.environ["CF_ACCOUNT_ID"]
API_TOKEN  = os.environ["CF_API_TOKEN"]
GRAPHQL    = "https://api.cloudflare.com/client/v4/graphql"

WORKERS_PRICES = {"requests": 0.30 / 1e6, "cpu_gb_sec": 0.02 / 1e6}
KV_PRICES      = {"reads": 0.50 / 1e6, "writes": 5.00 / 1e6}

def query(q, variables):
    r = requests.post(GRAPHQL,
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        json={"query": q, "variables": variables})
    r.raise_for_status()
    return r.json()

# ... build cost-by-script report and POST to Slack webhook
```

## Scheduled cost anomaly detection

Run a daily scheduled Worker to detect unusual spend spikes:

```typescript
// src/cost-monitor.ts
export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    const today  = new Date().toISOString().slice(0, 10);
    const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);

    // Compare today's D1 rows-read vs 7-day average
    const [current, baseline] = await Promise.all([
      queryD1Usage(env, today, today),
      queryD1Usage(env, sevenDaysAgo(), yesterday),
    ]);

    const ratio = current.rowsRead / (baseline.rowsRead / 7);
    if (ratio > 3) {
      await notify(env, `D1 rows read is ${ratio.toFixed(1)}x above 7-day average`);
    }
  },
};
```

```toml
# wrangler.toml
[triggers]
crons = ["0 8 * * *"]
```

## Anti-patterns

- Treating the monthly invoice as the primary cost signal — by the time the invoice
  arrives, the anomalous usage is weeks old. Use GraphQL daily.
- Sharing one Worker for many teams without naming conventions — you lose per-team
  attribution permanently; rename Workers before you need the data.
- Relying on KV writes for cost-proxy metrics — KV writes are $5/M, making them 10x
  more expensive than the requests they're tracking. Use Analytics Engine ($0 on Workers
  Paid plan) instead.
- Using per-request `fetch()` calls to send metrics — always use `ctx.waitUntil()` or
  batch writes via Analytics Engine to avoid slowing down the response path.

## Gotchas

- GraphQL Analytics data is available with up to a 10-minute delay; do not expect real-time
  cost data.
- D1 database IDs returned by the GraphQL API are UUIDs. Keep a separate mapping file
  (or use the naming convention above) to translate `database_id` → team/service.
- Analytics Engine datasets are scoped to the account. Data older than 90 days (or 180
  days on Enterprise) is automatically expired; export weekly summaries to R2 for
  long-term retention.
- R2 has no egress fee but Class A/B operations can dominate cost for high-churn
  buckets. Monitor `uploadCount` and `deleteCount` — aggressive upload/delete patterns
  (e.g., temp files) can cost more than storage.
- Workers CPU time billing (beyond the free tier included-CPU) requires the Workers Paid
  plan. On the Free plan, CPU time is not billed; cost is purely request-count.

## Verification

```bash
# Test GraphQL access returns data
curl -s -X POST https://api.cloudflare.com/client/v4/graphql \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"{ viewer { accounts(filter:{accountTag:\"'$CF_ACCOUNT_ID'\"}) { workersInvocationsAdaptive(limit:5 filter:{datetimeHour_geq:\"2026-08-21T00:00:00Z\"} orderBy:[sum_requests_DESC]) { sum { requests } dimensions { scriptName } } } } }"}' \
  | jq '.data.viewer.accounts[0].workersInvocationsAdaptive[:3]'

# Verify Analytics Engine dataset is receiving writes
# (after deploying the instrumented Worker, wait 1-2 min then query)
curl -s -X POST https://api.cloudflare.com/client/v4/graphql \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"{ viewer { accounts(filter:{accountTag:\"'$CF_ACCOUNT_ID'\"}) { workersAnalyticsEngineAdaptiveGroups(limit:5 filter:{datetimeHour_geq:\"2026-08-22T00:00:00Z\"} orderBy:[count_DESC]) { count dimensions { blob1 } } } } }"}' \
  | jq .
```

## Related

- cloudflare-workers-limits-resource-planning.md
- finops-real-time-cost-anomaly-detection.md
- aws-cost-explorer-tagging.md
- monitoring-sla-slo-sli.md
- workers-opentelemetry-tail-workers.md

## Sources

- https://developers.cloudflare.com/analytics/graphql-api/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/platform/pricing/
- https://developers.cloudflare.com/r2/pricing/
- https://developers.cloudflare.com/d1/platform/pricing/
- https://developers.cloudflare.com/kv/platform/pricing/
