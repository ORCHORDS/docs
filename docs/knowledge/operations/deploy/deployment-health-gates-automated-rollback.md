# Deployment Health Gates with Automated Rollback

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A deployment completes successfully (exit code 0 from Wrangler) but the new
Worker version introduces a regression: elevated error rates, p99 latency
spike, or increased rate of uncaught exceptions. Without automated health gates
the on-call engineer must manually detect the problem, decide to roll back, and
execute the rollback—a process that takes 5–30 minutes during which users are
affected. Health gates automate this detection-decision-action loop, reducing
the blast radius of bad deploys to a single observation window.

## Context

A health gate is a post-deploy verification step that:
1. Waits a configurable observation window after traffic shifts.
2. Queries one or more signal sources (error rate, latency, request success
   ratio) for the new version.
3. Compares observed values against pre-defined thresholds (SLOs).
4. Triggers automated rollback if any threshold is violated.

For Cloudflare Workers the primary signal sources are:
- **Cloudflare GraphQL Analytics API**: aggregated request/error metrics with
  ~1-minute granularity, queryable by script name and time range.
- **Wrangler tail**: real-time per-request stream (useful for the first 2–5
  minutes; see `wrangler-tail-logs-deployment-verification.md`).
- **Analytics Engine**: custom metrics written by the Worker itself (requires
  instrumentation).

Automated rollback on Workers means either:
- `wrangler rollback` (reverts to the previous deployment, 100 % traffic).
- `wrangler deployments create --version-id <prev> --version-percentage 100`
  (when using gradual rollouts with Workers Versions).

Health gate checks should run as a post-deploy CI step, as a standalone
GitHub Actions workflow triggered by the deployment event, or as a scheduled
Worker that polls metrics and triggers rollback via the Cloudflare API.

## Section 1: Defining Health Gate SLOs

Document thresholds explicitly in your project configuration so they are
version-controlled and reviewable in PRs.

### health-gate.config.json

```json
{
  "worker": "api-gateway",
  "observation_window_seconds": 300,
  "metrics": {
    "error_rate_threshold_pct": 2.0,
    "p99_latency_ms_threshold": 800,
    "success_rate_min_pct": 98.0
  },
  "rollback_on_violation": true,
  "alert_channels": ["slack"],
  "grace_period_seconds": 60
}
```

### SLO rationale

| Metric | Threshold | Rationale |
|---|---|---|
| Error rate | < 2 % | Baseline p50 error rate in steady state |
| p99 latency | < 800 ms | Users perceive > 1 s as slow; 800 ms leaves headroom |
| Success rate | > 98 % | Inverse of error rate; catches partial failure modes |
| Observation window | 5 min | Long enough to see a consistent signal; short enough to limit impact |
| Grace period | 60 s | Allows cold-start warming before measurement begins |

## Section 2: Querying Cloudflare Metrics and Making Rollback Decisions

### health-gate.mjs — post-deploy health gate script

```javascript
#!/usr/bin/env node
// health-gate.mjs
// Usage: WORKER=api-gateway node health-gate.mjs

import { readFileSync } from "node:fs";

const WORKER = process.env.WORKER ?? "api-gateway";
const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID;
const API_TOKEN = process.env.CLOUDFLARE_API_TOKEN;

const config = JSON.parse(
  readFileSync("health-gate.config.json", "utf8")
);

const {
  observation_window_seconds: WINDOW,
  grace_period_seconds: GRACE,
  metrics: THRESHOLDS,
  rollback_on_violation: AUTO_ROLLBACK,
} = config;

async function queryMetrics(workerName, windowSeconds) {
  const now = new Date();
  const start = new Date(now.getTime() - windowSeconds * 1000).toISOString();
  const end = now.toISOString();

  const query = `
    {
      viewer {
        accounts(filter: { accountTag: "${ACCOUNT_ID}" }) {
          workersInvocationsAdaptive(
            limit: 10000
            filter: {
              scriptName: "${workerName}"
              datetime_geq: "${start}"
              datetime_leq: "${end}"
            }
          ) {
            sum {
              requests
              errors
              subrequests
            }
            quantiles {
              cpuTimeP99
            }
          }
        }
      }
    }
  `;

  const resp = await fetch("https://api.cloudflare.com/client/v4/graphql", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query }),
  });

  const json = await resp.json();
  const data =
    json?.data?.viewer?.accounts?.[0]?.workersInvocationsAdaptive ?? [];

  const totals = data.reduce(
    (acc, row) => {
      acc.requests += row.sum.requests;
      acc.errors += row.sum.errors;
      acc.cpuP99 = Math.max(acc.cpuP99, row.quantiles?.cpuTimeP99 ?? 0);
      return acc;
    },
    { requests: 0, errors: 0, cpuP99: 0 }
  );

  return totals;
}

async function triggerRollback(workerName) {
  console.error(`[GATE] Triggering rollback for ${workerName}...`);
  const { execSync } = await import("node:child_process");
  execSync(`wrangler rollback --name ${workerName} --message "Health gate rollback"`, {
    stdio: "inherit",
    env: process.env,
  });
  console.error(`[GATE] Rollback complete.`);
}

async function main() {
  console.log(`[GATE] Grace period: ${GRACE}s...`);
  await new Promise((r) => setTimeout(r, GRACE * 1000));

  console.log(`[GATE] Observing ${WORKER} for ${WINDOW}s...`);
  await new Promise((r) => setTimeout(r, WINDOW * 1000));

  const metrics = await queryMetrics(WORKER, WINDOW);
  console.log(`[GATE] metrics:`, JSON.stringify(metrics, null, 2));

  if (metrics.requests === 0) {
    console.warn("[GATE] No requests observed — skipping gate (no traffic).");
    process.exit(0);
  }

  const errorRatePct = (metrics.errors / metrics.requests) * 100;
  const successRatePct = 100 - errorRatePct;

  const violations = [];

  if (errorRatePct > THRESHOLDS.error_rate_threshold_pct) {
    violations.push(
      `error_rate=${errorRatePct.toFixed(2)}% > threshold=${THRESHOLDS.error_rate_threshold_pct}%`
    );
  }

  if (successRatePct < THRESHOLDS.success_rate_min_pct) {
    violations.push(
      `success_rate=${successRatePct.toFixed(2)}% < threshold=${THRESHOLDS.success_rate_min_pct}%`
    );
  }

  if (violations.length > 0) {
    console.error(`[GATE] VIOLATIONS DETECTED:\n  - ${violations.join("\n  - ")}`);

    if (AUTO_ROLLBACK) {
      await triggerRollback(WORKER);
    }

    process.exit(1);
  }

  console.log(
    `[GATE] PASS: error_rate=${errorRatePct.toFixed(2)}%, ` +
    `success_rate=${successRatePct.toFixed(2)}%`
  );
  process.exit(0);
}

main().catch((err) => {
  console.error("[GATE] Unexpected error:", err);
  process.exit(2);
});
```

## Section 3: GitHub Actions Integration

### Full deploy + health gate workflow

```yaml
# .github/workflows/deploy-with-gate.yml
name: Deploy with Health Gate

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm

      - name: Install dependencies
        run: npm ci

      - name: Build
        run: npm run build

      - name: Deploy to Cloudflare Workers
        id: deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          wrangler deploy --name api-gateway --env production
          echo "deployed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$GITHUB_OUTPUT"

      - name: Run health gate
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          WORKER: api-gateway
        run: node scripts/health-gate.mjs

      - name: Notify on rollback
        if: failure()
        uses: slackapi/slack-github-action@v1
        with:
          payload: |
            {
              "text": ":rotating_light: Health gate triggered rollback for api-gateway. Deploy SHA: ${{ github.sha }}"
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_DEPLOY_WEBHOOK }}
```

### Gradual rollout variant with staged health gates

```yaml
# Health gate at each traffic level before promoting further
- name: Shift 10 % traffic to new version
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
  run: |
    NEW_VERSION=$(wrangler versions list --name api-gateway --json | jq -r 'last | .id')
    OLD_VERSION=$(wrangler versions list --name api-gateway --json | jq -r '.[-2] | .id')
    wrangler deployments create \
      --version-id "$NEW_VERSION" --version-percentage 10 \
      --version-id "$OLD_VERSION" --version-percentage 90

- name: Health gate at 10 %
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
    WORKER: api-gateway
  run: GATE_WINDOW=120 node scripts/health-gate.mjs

- name: Promote to 100 %
  if: success()
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
  run: |
    NEW_VERSION=$(wrangler versions list --name api-gateway --json | jq -r 'last | .id')
    wrangler deployments create \
      --version-id "$NEW_VERSION" --version-percentage 100
```

## Anti-patterns

- **Setting thresholds too loose during initial configuration**: start with
  historical p95/p99 values plus a 20 % tolerance, not arbitrary round numbers
  (e.g., "50 % error rate is fine"). A gate that never fires gives false
  confidence.

- **Using health gate window < 60 seconds**: Workers metrics in the GraphQL API
  lag by 1–2 minutes. A 30-second gate will query before data is available and
  see zero requests, causing the gate to pass vacuously.

- **Treating a health gate pass as a quality guarantee**: gates detect aggregate
  regressions; they miss correctness bugs that don't manifest as errors within
  the observation window. Gates are a safety net, not a replacement for testing.

- **Running automated rollback on the same commit that caused the failure
  without investigation**: add a circuit breaker—if the rolled-back version also
  fails a health gate, pause automated rollback and page on-call instead.

- **Storing health gate thresholds in CI secrets rather than source control**:
  thresholds should be reviewed and version-controlled. Only credentials should
  be in secrets.

## Gotchas

- `wrangler rollback` reverts to the most recent previous deployment. If
  multiple bad deploys happen in quick succession, it will roll back to the
  second-bad version. Pin the stable version ID explicitly:
  `wrangler rollback --deployment-id <stable-id>`.

- The Cloudflare Workers Analytics GraphQL API returns data at 1-minute
  granularity. For Workers under very low traffic (< 10 req/min), the error
  rate signal is noisy. Consider setting minimum request count thresholds
  before gating.

- `wrangler rollback` requires the `Workers Scripts Write` permission on the API
  token. Verify the token used in CI has this permission before a real incident.

- CPU time (from `quantiles.cpuTimeP99`) is not wall-clock latency. Use
  Cloudflare Zone Analytics or synthetic probes for end-to-end latency
  measurement.

## Verification

```bash
# Verify wrangler rollback is authorized with the current token
wrangler rollback --name api-gateway --dry-run 2>/dev/null || \
  echo "Dry-run not supported; check token permissions"

# Manually test the health gate against the current deployment
WORKER=api-gateway \
CLOUDFLARE_API_TOKEN=$CF_API_TOKEN \
CLOUDFLARE_ACCOUNT_ID=$CF_ACCOUNT_ID \
  node scripts/health-gate.mjs

# Inspect recent deployment history to identify stable version for explicit rollback
wrangler deployments list --name api-gateway | head -20
```

## Related

- `rollback-decision-automation-slo-monitoring.md`
- `rollback-strategies-workers-pages.md`
- `wrangler-tail-logs-deployment-verification.md`
- `slo-alerting-thresholds.md`
- `canary-workers-gradual-traffic-split.md`
- `deploy-gate-antipatterns.md`

## Sources

- Cloudflare Workers analytics via GraphQL: https://developers.cloudflare.com/analytics/graphql-api/
- wrangler rollback command: https://developers.cloudflare.com/workers/wrangler/commands/#rollback
- Workers Versions gradual deployments: https://developers.cloudflare.com/workers/configuration/versions-and-deployments/gradual-deployments/
- Workers metrics fields: https://developers.cloudflare.com/analytics/graphql-api/features/data-sets/workers-metrics/
