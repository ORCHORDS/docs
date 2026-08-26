# Workers Gradual Traffic Migration with Weighted Routing

- **Date:** 2026-08-24
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

You are migrating traffic from a legacy Worker script (`payments-v1`) to a rewritten Worker (`payments-v2`) that shares no code lineage. You cannot use the Versions API's canary feature because the two Workers have different `wrangler.toml` names and different KV/D1 bindings. You need a controlled, percentage-based migration that can be paused or reversed instantly, with automated error-rate gates at each traffic tier.

---

## Context

Cloudflare Workers supports weighted routing between distinct Worker scripts through **route-level traffic splitting** using the Workers REST API or by deploying a thin **router Worker** that inspects a stable shard key (tenant ID, user ID modulo, or a persistent cookie) and dispatches to the target Worker via a service binding. This pattern differs from the Versions API's percentage rollout (which is always within a single script) — here, two independently deployed, differently-named Workers split real traffic, with the router controlling the migration percentage via a KV flag that can be updated without a redeploy.

---

## 1. Architecture Overview

```
         ┌─────────────────────────────────────┐
         │          Router Worker               │
         │  (traffic-migrator)                  │
         │                                      │
         │  KV: { "v2_percent": "25" }          │
         │                                      │
         │  deterministic_bucket(request)       │
         │    < 25% → payments-v2               │
         │    >= 25% → payments-v1 (legacy)     │
         └──────────────┬──────────────────────┘
                        │  Service Bindings
              ┌─────────┴──────────┐
       ┌──────▼──────┐     ┌──────▼──────┐
       │ payments-v1 │     │ payments-v2 │
       │  (legacy)   │     │  (rewrite)  │
       └─────────────┘     └─────────────┘
```

The router Worker reads a KV percentage value and uses a deterministic hash of a stable request property (session cookie or user ID) to ensure a given user is always routed to the same backend during the migration window.

---

## 2. Router Worker `wrangler.toml`

```toml
# traffic-migrator/wrangler.toml
name = "traffic-migrator"
main = "src/index.ts"
compatibility_date = "2026-07-01"

routes = [
  { pattern = "api.example.com/payments/*", zone_name = "example.com" }
]

[[kv_namespaces]]
binding = "MIGRATION_FLAGS"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"   # replace with real KV namespace ID

[[services]]
binding = "PAYMENTS_V1"
service = "payments-v1"
entrypoint = "default"

[[services]]
binding = "PAYMENTS_V2"
service = "payments-v2"
entrypoint = "default"
```

---

## 3. Router Worker Implementation

```typescript
// traffic-migrator/src/index.ts
export interface Env {
  MIGRATION_FLAGS: KVNamespace;
  PAYMENTS_V1: Fetcher;
  PAYMENTS_V2: Fetcher;
}

/**
 * Deterministic shard: maps a stable key to [0, 100).
 * Same key always lands on the same bucket across requests.
 */
async function deterministicBucket(key: string): Promise<number> {
  const encoder = new TextEncoder();
  const data = encoder.encode(key);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = new Uint8Array(hashBuffer);
  // Use first 4 bytes as uint32, mod 100
  const view = new DataView(hashBuffer);
  return view.getUint32(0) % 100;
}

function extractShardKey(request: Request): string {
  const url = new URL(request.url);
  // Prefer stable user identifier from session cookie
  const cookieHeader = request.headers.get("Cookie") ?? "";
  const sessionMatch = cookieHeader.match(/session_id=([^;]+)/);
  if (sessionMatch) return sessionMatch[1];

  // Fall back to Authorization bearer token subject (first 16 chars of JWT payload)
  const auth = request.headers.get("Authorization") ?? "";
  if (auth.startsWith("Bearer ")) {
    const token = auth.slice(7);
    const parts = token.split(".");
    if (parts.length === 3) return parts[1].slice(0, 16);
  }

  // Last resort: IP address (not stable behind NAT/proxies)
  return request.headers.get("CF-Connecting-IP") ?? url.pathname;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Read migration percentage from KV (cached for 10s per PoP)
    const percentStr = await env.MIGRATION_FLAGS.get("v2_percent", {
      cacheTtl: 10,
    });
    const v2Percent = Math.max(0, Math.min(100, parseInt(percentStr ?? "0", 10)));

    const shardKey = extractShardKey(request);
    const bucket = await deterministicBucket(shardKey);

    const useV2 = bucket < v2Percent;
    const target = useV2 ? env.PAYMENTS_V2 : env.PAYMENTS_V1;
    const targetName = useV2 ? "v2" : "v1";

    // Add routing metadata header for observability (stripped at edge before client)
    const modifiedRequest = new Request(request, {
      headers: new Headers({
        ...Object.fromEntries(request.headers),
        "X-Migration-Target": targetName,
        "X-Migration-Bucket": String(bucket),
        "X-Migration-Percent": String(v2Percent),
      }),
    });

    const response = await target.fetch(modifiedRequest);

    // Log routing decision for Analytics Engine (fire-and-forget)
    ctx.waitUntil(
      logRoutingDecision(targetName, v2Percent, response.status)
    );

    return response;
  },
} satisfies ExportedHandler<Env>;

async function logRoutingDecision(
  target: string,
  percent: number,
  status: number
): Promise<void> {
  // Structured log picked up by wrangler tail / Logpush
  console.log(
    JSON.stringify({ event: "traffic_migration", target, percent, status })
  );
}
```

---

## 4. Migration Percentage Control Script

```typescript
// scripts/set-migration-percent.ts
// Usage: npx tsx scripts/set-migration-percent.ts --env production --percent 25

import { parseArgs } from "node:util";

const { values } = parseArgs({
  args: process.argv.slice(2),
  options: {
    env: { type: "string", default: "production" },
    percent: { type: "string" },
  },
});

const percent = parseInt(values.percent ?? "", 10);
if (isNaN(percent) || percent < 0 || percent > 100) {
  console.error("--percent must be an integer between 0 and 100");
  process.exit(1);
}

const accountId = process.env.CF_ACCOUNT_ID!;
const namespaceId = process.env.MIGRATION_KV_NAMESPACE_ID!;
const apiToken = process.env.CF_API_TOKEN!;

const url = `https://api.cloudflare.com/client/v4/accounts/${accountId}/storage/kv/namespaces/${namespaceId}/values/v2_percent`;

const res = await fetch(url, {
  method: "PUT",
  headers: {
    Authorization: `Bearer ${apiToken}`,
    "Content-Type": "text/plain",
  },
  body: String(percent),
});

if (!res.ok) {
  console.error("Failed to update KV:", await res.text());
  process.exit(1);
}

console.log(`Migration percentage set to ${percent}% → v2`);
```

---

## 5. GitHub Actions: Staged Migration Pipeline

```yaml
# .github/workflows/traffic-migration.yml
name: Staged Traffic Migration

on:
  workflow_dispatch:
    inputs:
      target_percent:
        description: "Percentage to route to v2 (0-100)"
        required: true
        default: "10"

jobs:
  migrate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set migration percentage
        env:
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          MIGRATION_KV_NAMESPACE_ID: ${{ secrets.MIGRATION_KV_NAMESPACE_ID }}
        run: |
          npx tsx scripts/set-migration-percent.ts \
            --percent ${{ github.event.inputs.target_percent }}

      - name: Wait for KV propagation
        run: sleep 15

      - name: Run smoke tests against live traffic split
        env:
          TARGET_PERCENT: ${{ github.event.inputs.target_percent }}
        run: |
          # Fire 100 requests and confirm ~TARGET_PERCENT% reach v2
          node scripts/validate-migration-split.mjs \
            --expected-percent "$TARGET_PERCENT" \
            --tolerance 5 \
            --requests 100

      - name: Check error rate (fail fast)
        run: |
          # Query Workers Analytics Engine for 5xx rate in last 2 minutes
          node scripts/check-error-rate.mjs \
            --max-error-rate 0.01 \
            --window-minutes 2
```

---

## 6. Emergency Rollback to 0% v2 Traffic

```bash
#!/usr/bin/env bash
# scripts/migration-rollback.sh — run immediately on incident declaration
set -euo pipefail

echo "Rolling back: setting v2 traffic to 0%..."

curl -s -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${MIGRATION_KV_NAMESPACE_ID}/values/v2_percent" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: text/plain" \
  -d "0" \
  | grep -q '"success":true' && echo "Rollback complete: 100% traffic on v1" || echo "KV write failed — check credentials"
```

The KV write propagates to all Cloudflare PoPs within ~15 seconds. The router Worker's `cacheTtl: 10` means full rollback is effective within 25 seconds worst-case.

---

## Anti-patterns

- **Random routing per request** — a user mid-checkout is sent to v1 for cart, v2 for payment, then v1 for order confirmation. Use a stable shard key (session ID or user ID) for consistent routing within a session.
- **Reading the KV flag without a `cacheTtl`** — unbounded KV reads at high request rates hit KV read limits. A 10-second `cacheTtl` gives a safe buffer.
- **Migrating 0% → 100% in one step** — always use incremental tiers: 1% → 5% → 25% → 50% → 100% with error-rate gates between each tier.
- **Deleting the router Worker before confirming v2 is stable at 100%** — the router is the rollback mechanism. Keep it deployed until v2 has run at 100% for at least 48 hours.

---

## Gotchas

- Service bindings between the router and target Workers require all three Workers (`traffic-migrator`, `payments-v1`, `payments-v2`) to be in the same Cloudflare account.
- KV `cacheTtl` is per-PoP, not global. Changes to the migration percentage take up to `cacheTtl` seconds to reach all PoPs. Do not set it below 5 seconds or you risk KV rate limits.
- The `X-Migration-Target` header set by the router must be stripped before response headers reach the client. Use a Cloudflare Transform Rule or strip it in the response path.
- At exactly 0% or 100%, consider removing the router entirely and deploying the target directly to the route to eliminate an extra network hop.

---

## Verification

```bash
# 1. Confirm current migration percentage in KV
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${MIGRATION_KV_NAMESPACE_ID}/values/v2_percent" \
  -H "Authorization: Bearer ${CF_API_TOKEN}"

# 2. Tail router logs to see routing decisions in real time
wrangler tail traffic-migrator --format=json \
  | jq 'select(.logs[].message[] | contains("traffic_migration"))'

# 3. Verify shard determinism (same IP always hits same backend)
for i in {1..5}; do
  curl -s -I https://api.example.com/payments/test \
    | grep -i x-migration-target
done
```

---

## Related

- `canary-workers-gradual-traffic-split.md` — canary deployments within a single Worker script using the Versions API
- `worker-versioning-gradual-rollout.md` — gradual rollout using wrangler versions percentage flags
- `blue-green-deploy-cloudflare-workers.md` — binary traffic switch between two Workers
- `workers-service-bindings-deployment-ordering.md` — deployment ordering when Workers depend on service bindings
- `feature-flag-deployment-gates-cloudflare-kv.md` — KV-backed feature flags for deployment gating

---

## Sources

- Cloudflare Docs — Service Bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Cloudflare Docs — KV API: https://developers.cloudflare.com/kv/api/
- Cloudflare Docs — Workers Routes: https://developers.cloudflare.com/workers/configuration/routing/routes/
