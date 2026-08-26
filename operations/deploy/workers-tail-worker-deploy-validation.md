# Workers Tail Worker Deploy Validation

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
After deploying a Cloudflare Worker, teams need structured post-deploy observability that captures request traces, error rates, and response latencies without relying solely on `wrangler tail` CLI sessions that terminate when a terminal closes.

## Context
Cloudflare Tail Workers are a separate Worker bound as a `tail_consumers` entry in `wrangler.toml`. They receive a batch of `TraceItem` objects after each invocation of the observed Worker, enabling persistent, programmable telemetry — writing to D1, Analytics Engine, or an external logging endpoint. This pattern complements deploy pipelines by providing automated, always-on validation data rather than manual log inspection.

## Tail Consumer wrangler.toml Configuration

```toml
# Primary worker — wrangler.toml
name = "orchords-api"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[tail_consumers]]
service = "orchords-tail"
```

```toml
# Tail worker — tail/wrangler.toml
name = "orchords-tail"
main = "src/tail.ts"
compatibility_date = "2026-08-01"

[[analytics_engine_datasets]]
binding = "TELEMETRY"
dataset = "deploy_traces"
```

## Tail Worker Implementation

```typescript
// tail/src/tail.ts
export interface Env {
  TELEMETRY: AnalyticsEngineDataset;
}

interface TraceLog {
  message: unknown[];
  level: string;
  timestamp: number;
}

interface TraceException {
  message: string;
  timestamp: number;
}

interface TraceItem {
  event: {
    request?: { url: string; method: string };
    response?: { status: number };
  } | null;
  eventTimestamp: number | null;
  logs: TraceLog[];
  exceptions: TraceException[];
  scriptName: string | null;
  outcome: "ok" | "exception" | "exceededCpu" | "exceededMemory" | "unknown";
}

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      const url = event.event?.request?.url ?? "";
      const method = event.event?.request?.method ?? "UNKNOWN";
      const status = event.event?.response?.status ?? 0;
      const outcome = event.outcome;
      const errorCount = event.exceptions.length;
      const latencyMs = event.eventTimestamp
        ? Date.now() - event.eventTimestamp
        : -1;

      env.TELEMETRY.writeDataPoint({
        blobs: [url, method, outcome, event.scriptName ?? ""],
        doubles: [status, errorCount, latencyMs],
        indexes: [outcome],
      });

      if (outcome !== "ok" || errorCount > 0) {
        console.error(
          JSON.stringify({
            type: "deploy_anomaly",
            url,
            status,
            outcome,
            errors: event.exceptions.map((e) => e.message),
            ts: new Date().toISOString(),
          })
        );
      }
    }
  },
};
```

## Deploy-Time Error Rate Gate

Query Analytics Engine after each deploy to assert error rate stays below threshold.

```typescript
// scripts/deploy-gate.ts — run with npx tsx after deploying
const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const CF_API_TOKEN = process.env.CF_API_TOKEN!;
const DATASET = "deploy_traces";
const ERROR_RATE_THRESHOLD = 0.02; // 2%
const WINDOW_MINUTES = 5;

async function queryErrorRate(): Promise<number> {
  const query = `
    SELECT
      SUM(_sample_interval) AS total,
      SUM(IF(blob3 != 'ok', _sample_interval, 0)) AS errors
    FROM ${DATASET}
    WHERE timestamp > NOW() - INTERVAL '${WINDOW_MINUTES}' MINUTE
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
    }
  );

  const data = (await resp.json()) as {
    data: Array<{ total: number; errors: number }>;
  };
  const row = data.data[0];
  if (!row || row.total === 0) return 0;
  return row.errors / row.total;
}

async function main(): Promise<void> {
  console.log(`Waiting ${WINDOW_MINUTES}m for tail data to accumulate...`);
  await new Promise((r) => setTimeout(r, WINDOW_MINUTES * 60 * 1000));

  const rate = await queryErrorRate();
  console.log(`Post-deploy error rate: ${(rate * 100).toFixed(2)}%`);

  if (rate > ERROR_RATE_THRESHOLD) {
    console.error(`Error rate ${rate} exceeds threshold ${ERROR_RATE_THRESHOLD}. Failing deploy.`);
    process.exit(1);
  }
  console.log("Error rate within acceptable range. Deploy validated.");
}

main();
```

## Tail Worker Deployment Order

The tail consumer must exist before the primary Worker is deployed. A race condition occurs when both are deployed in the same pipeline step.

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "1. Deploy tail consumer first"
cd tail && npx wrangler deploy && cd ..

echo "2. Wait for tail worker to propagate"
sleep 5

echo "3. Deploy primary worker (now has a valid tail consumer)"
npx wrangler deploy

echo "4. Send synthetic requests to prime telemetry"
for i in $(seq 1 20); do
  curl -s "https://orchords-api.orchords-api.workers.dev/health" > /dev/null
done

echo "5. Run deploy gate"
npx tsx scripts/deploy-gate.ts
```

## Anti-patterns
- Relying solely on `wrangler tail` CLI — sessions are ephemeral and not suitable for automated gates
- Deploying the tail consumer after the primary Worker — the binding silently fails for requests in the gap
- Writing raw PII (user emails, IPs) to Analytics Engine datasets without scrubbing
- Querying the dataset too soon after deploy — Analytics Engine has ~1–2 minute ingestion lag
- Using `console.log` in the tail worker for all events — tail workers cannot be tailed themselves, so logs are only visible in Logpush

## Gotchas
- Tail Workers count against your Worker invocation quota at 1:1 with the observed Worker
- A tail Worker that throws or times out silently drops its trace batch — add a top-level try/catch
- `event.eventTimestamp` is the wall-clock time of the observed request, not the tail invocation time
- Analytics Engine `writeDataPoint` is best-effort; under extreme load some points may be dropped
- Tail Workers do not receive traces for subrequests (`fetch()` calls inside the observed Worker)

## Verification
```bash
# Check tail binding is registered
npx wrangler tail orchords-api --once --format json | jq '.scriptName'

# Query Analytics Engine for recent error outcomes
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{"query": "SELECT blob3, COUNT() FROM deploy_traces WHERE timestamp > NOW() - INTERVAL '\''10'\'' MINUTE GROUP BY blob3"}'
```

## Related
- `wrangler-tail-logs-deployment-verification.md`
- `cloudflare-analytics-engine-deploy-observability.md`
- `canary-workers-gradual-traffic-split.md`
- `deployment-health-gates-automated-rollback.md`

## Sources
- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/wrangler/configuration/#tail_consumers
