# Canary Percentage Routing for Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to deploy a new version of a Worker to a small slice of production traffic before rolling it out fully. Instead of an all-or-nothing deploy you need to ramp from 1 % to 100 % while watching error rates, with an automated rollback trigger if anything degrades.

---

## Context

Cloudflare Workers support multiple named environments in `wrangler.toml`, and service bindings let one Worker call another. By deploying the new version to a `canary` environment and keeping the old version in `production`, a thin router Worker can split traffic by reading a `CANARY_PERCENTAGE` value from KV and comparing it to `Math.random()`. Analytics Engine records every routed request so a monitoring script can compute p99 error rates and automatically flip the percentage back to 0 when a threshold is breached. The KV value is the single source of truth, so ramping or rolling back is an atomic key update with no re-deploy required.

---

## Section 1 — Config / wrangler.toml

```toml
name = "router"
main = "src/router.ts"
compatibility_date = "2026-08-01"

[[kv_namespaces]]
binding = "CANARY_KV"
id = "<your-kv-namespace-id>"

[[analytics_engine_datasets]]
binding = "AE"
dataset = "canary_routing"

[env.production]
name = "api-production"
main = "src/worker.ts"

[env.canary]
name = "api-canary"
main = "src/worker.ts"

# Service bindings wired into the router
[[services]]
binding = "PRODUCTION_WORKER"
service = "api-production"

[[services]]
binding = "CANARY_WORKER"
service = "api-canary"
```

---

## Section 2 — Implementation / Router Worker

```typescript
// src/router.ts
export interface Env {
  CANARY_KV: KVNamespace;
  CANARY_WORKER: Fetcher;
  PRODUCTION_WORKER: Fetcher;
  AE: AnalyticsEngineDataset;
}

const DEFAULT_CANARY_PERCENTAGE = 0;

async function getCanaryPercentage(kv: KVNamespace): Promise<number> {
  const raw = await kv.get("CANARY_PERCENTAGE");
  if (raw === null) return DEFAULT_CANARY_PERCENTAGE;
  const parsed = parseFloat(raw);
  return Number.isFinite(parsed) ? Math.min(Math.max(parsed, 0), 100) : DEFAULT_CANARY_PERCENTAGE;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const percentage = await getCanaryPercentage(env.CANARY_KV);
    const useCanary = Math.random() * 100 < percentage;
    const target = useCanary ? "canary" : "production";

    const startMs = Date.now();
    let status = 200;

    try {
      const response = useCanary
        ? await env.CANARY_WORKER.fetch(request.clone())
        : await env.PRODUCTION_WORKER.fetch(request.clone());

      status = response.status;

      ctx.waitUntil(
        env.AE.writeDataPoint({
          blobs: [target, new URL(request.url).pathname],
          doubles: [Date.now() - startMs, status >= 500 ? 1 : 0],
          indexes: [target],
        })
      );

      return response;
    } catch (err) {
      ctx.waitUntil(
        env.AE.writeDataPoint({
          blobs: [target, new URL(request.url).pathname],
          doubles: [Date.now() - startMs, 1],
          indexes: [target],
        })
      );
      throw err;
    }
  },
};
```

---

## Section 3 — CI / Automation

```yaml
# .github/workflows/canary-deploy.yml
name: Canary Deploy

on:
  push:
    branches: [main]

jobs:
  deploy-canary:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Install wrangler
        run: npm install -g wrangler

      - name: Deploy canary environment
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: wrangler deploy --env canary

      - name: Set canary percentage to 1 %
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: |
          wrangler kv:key put \
            --namespace-id=${{ secrets.KV_NAMESPACE_ID }} \
            CANARY_PERCENTAGE "1"

      - name: Wait 5 minutes and check error rate
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          sleep 300
          ERROR_RATE=$(node scripts/check-error-rate.mjs canary 5)
          echo "Canary error rate: ${ERROR_RATE}%"
          if (( $(echo "$ERROR_RATE > 1" | bc -l) )); then
            echo "ERROR: canary error rate ${ERROR_RATE}% exceeds 1% threshold — rolling back"
            wrangler kv:key put \
              --namespace-id=${{ secrets.KV_NAMESPACE_ID }} \
              CANARY_PERCENTAGE "0"
            exit 1
          fi
          echo "Canary healthy — ramping to 10%"
          wrangler kv:key put \
            --namespace-id=${{ secrets.KV_NAMESPACE_ID }} \
            CANARY_PERCENTAGE "10"
```

```javascript
// scripts/check-error-rate.mjs  (Node 20+)
import { strict as assert } from "assert";

const [, , target = "canary", windowMinutes = "5"] = process.argv;

const accountId = process.env.CF_ACCOUNT_ID;
const apiToken = process.env.CLOUDFLARE_API_TOKEN;
assert(accountId && apiToken, "CF_ACCOUNT_ID and CLOUDFLARE_API_TOKEN must be set");

const query = `
  SELECT
    SUM(_sample_interval * double2) AS errors,
    SUM(_sample_interval)           AS total
  FROM canary_routing
  WHERE blob1 = '${target}'
    AND timestamp >= NOW() - INTERVAL '${windowMinutes}' MINUTE
`;

const res = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
  {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query }),
  }
);

const json = await res.json();
assert(json.success, `Analytics Engine query failed: ${JSON.stringify(json.errors)}`);

const row = json.result?.data?.[0] ?? { errors: 0, total: 0 };
const rate = row.total === 0 ? 0 : (row.errors / row.total) * 100;
console.log(rate.toFixed(4));
```

---

## Anti-patterns

- **Reading canary percentage on every request without caching** — each request hits KV and adds latency; cache the value in memory for 5–10 seconds with a module-level variable and a timestamp.
- **Deploying the router and the canary in the same step** — the service binding must resolve, so always deploy `api-canary` before the router; combine in CI with sequential wrangler calls.
- **Using `Math.random()` for sticky sessions** — random routing means the same user can hit both versions in the same session; use a hashed cookie or `cf.clientIp` when session consistency matters.
- **Setting CANARY_PERCENTAGE to a non-numeric string** — the router silently falls back to 0 %; validate the value in the KV write script rather than only in the read path.

---

## Gotchas

- KV has eventual consistency across regions; a percentage write may take up to 60 seconds to propagate globally. Do not expect an instant cut-off.
- Service bindings count as subrequests; Cloudflare's limit is 1 000 subrequests per Worker invocation. The router itself counts as one level, so nested bindings reduce available headroom.
- Analytics Engine data points are sampled; very low-traffic canaries (<100 req/min) may show misleading error rates. Add a minimum-request guard in `check-error-rate.mjs`.
- `wrangler kv:key put` with `--namespace-id` requires the `Account:KV Storage:Edit` permission on the API token.

---

## Verification

```bash
# Check current canary percentage
wrangler kv:key get --namespace-id=<id> CANARY_PERCENTAGE

# Deploy canary build
wrangler deploy --env canary

# Manually set to 5 %
wrangler kv:key put --namespace-id=<id> CANARY_PERCENTAGE "5"

# Tail router logs in real time
wrangler tail router

# Rollback: set back to 0 %
wrangler kv:key put --namespace-id=<id> CANARY_PERCENTAGE "0"

# Query error rate from Analytics Engine (last 10 min)
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT SUM(_sample_interval*double2)/SUM(_sample_interval)*100 AS err_pct FROM canary_routing WHERE blob1=\'canary\' AND timestamp>=NOW()-INTERVAL \'10\' MINUTE"}' \
  | jq '.result.data'
```

---

## Related

- `workers-blue-green-deployment-kv-feature-flags.md`
- `workers-rollback-wrangler-versions.md`
- `workers-deployment-smoke-test-health-check.md`

---

## Sources

- Cloudflare Workers Service Bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Cloudflare Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare KV — https://developers.cloudflare.com/kv/
- Wrangler CLI reference — https://developers.cloudflare.com/workers/wrangler/commands/
