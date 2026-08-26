# Traffic Splitting for A/B Deployments with Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to roll out a new Worker version to a percentage of traffic — 5% initially, then 25%, then 100% — without full blue/green deploys. Routing must be deterministic per user (a user always sees the same variant), conversion must be tracked per variant, and you need automatic rollback if the new variant's error rate spikes.

## Context

Cloudflare Workers support this pattern entirely at the edge using:
1. **Service Bindings** — two named Workers (variant A and variant B) bound into a router Worker; the router picks one per request.
2. **KV** — stores the current rollout percentage (updated without redeploying the router).
3. **Analytics Engine** — records variant assignment and conversion events per request.
4. **Hash-based routing** — deterministic user bucket assignment via a hash of the user ID or session cookie, so the same user always gets the same variant.

Automatic rollback is implemented by a cron-triggered Worker that reads Analytics Engine data, computes error rates per variant, and updates the KV rollout percentage back to 0 if variant B exceeds a threshold.

## Solution

```typescript
// src/router.ts — the traffic-splitting router Worker
export interface Env {
  // Service bindings to the two variants
  VARIANT_A: Fetcher;       // existing stable Worker
  VARIANT_B: Fetcher;       // new candidate Worker

  // KV stores rollout config: { percentage: number }
  ROLLOUT_CONFIG: KVNamespace;

  // Analytics Engine for measuring variants
  ANALYTICS: AnalyticsEngineDataset;

  ENVIRONMENT: string;
}

interface RolloutConfig {
  percentage: number;     // 0-100: % of traffic routed to variant B
  updatedAt: string;
  updatedBy: string;
}

async function getRolloutPercentage(kv: KVNamespace): Promise<number> {
  try {
    const raw = await kv.get("rollout", { type: "json" }) as RolloutConfig | null;
    return raw?.percentage ?? 0;
  } catch {
    // Fail open — default to variant A (stable)
    return 0;
  }
}

// Deterministic hash-based bucket assignment (0–99)
function getUserBucket(userId: string): number {
  // FNV-1a 32-bit hash for speed and reasonable distribution
  let hash = 2166136261;
  for (let i = 0; i < userId.length; i++) {
    hash ^= userId.charCodeAt(i);
    hash = (hash * 16777619) >>> 0; // keep 32-bit unsigned
  }
  return hash % 100;
}

function extractUserId(request: Request): string {
  // Try Authorization header first
  const auth = request.headers.get("Authorization");
  if (auth?.startsWith("Bearer ")) {
    // Extract sub claim without full JWT verification (perf: use a KV-cached parse)
    try {
      const payload = JSON.parse(atob(auth.split(".")[1]));
      if (payload.sub) return payload.sub;
    } catch { /* fall through */ }
  }

  // Fall back to session cookie
  const cookie = request.headers.get("Cookie") ?? "";
  const match = cookie.match(/session=([^;]+)/);
  if (match) return match[1];

  // Last resort: IP-based (not sticky across IPs, acceptable for anonymous users)
  return request.headers.get("CF-Connecting-IP") ?? "unknown";
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const userId = extractUserId(request);
    const bucket = getUserBucket(userId);
    const rolloutPct = await getRolloutPercentage(env.ROLLOUT_CONFIG);

    const variant: "a" | "b" = bucket < rolloutPct ? "b" : "a";
    const variantFetcher = variant === "b" ? env.VARIANT_B : env.VARIANT_A;

    // Record assignment event
    env.ANALYTICS.writeDataPoint({
      blobs: [userId, request.url, request.method, variant],
      doubles: [bucket, rolloutPct],
      indexes: [variant], // enables fast per-variant queries
    });

    const startMs = Date.now();
    let response: Response;
    let errorOccurred = false;

    try {
      response = await variantFetcher.fetch(request);

      if (response.status >= 500) {
        errorOccurred = true;
      }
    } catch (err) {
      errorOccurred = true;
      // Fallback to variant A on variant B failure
      if (variant === "b") {
        response = await env.VARIANT_A.fetch(request);
      } else {
        throw err;
      }
    }

    const durationMs = Date.now() - startMs;

    // Record outcome event
    env.ANALYTICS.writeDataPoint({
      blobs: [userId, "outcome", variant, errorOccurred ? "error" : "ok"],
      doubles: [durationMs, errorOccurred ? 1 : 0],
      indexes: [variant],
    });

    // Attach variant info headers for debugging (strip in prod if desired)
    const headers = new Headers(response!.headers);
    if (env.ENVIRONMENT !== "production") {
      headers.set("X-Variant", variant);
      headers.set("X-Bucket", String(bucket));
      headers.set("X-Rollout-Pct", String(rolloutPct));
    }

    return new Response(response!.body, {
      status: response!.status,
      statusText: response!.statusText,
      headers,
    });
  },
};
```

```typescript
// src/conversion.ts — record conversion events from the target Workers
// Called by variant Workers when a conversion occurs (e.g., checkout complete)
export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

export async function recordConversion(
  env: Env,
  userId: string,
  variant: string,
  conversionType: string,
  value: number
): Promise<void> {
  env.ANALYTICS.writeDataPoint({
    blobs: [userId, "conversion", conversionType, variant],
    doubles: [value, 1],
    indexes: [variant],
  });
}
```

```typescript
// src/rollback-cron.ts — automatic rollback cron Worker
export interface Env {
  ROLLOUT_CONFIG: KVNamespace;
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;            // secret — Analytics Engine query requires API access
  ERROR_RATE_THRESHOLD: string;   // e.g. "0.05" = 5%
  ANALYTICS_DATASET: string;      // Analytics Engine dataset name
}

async function queryVariantErrorRate(
  env: Env,
  variant: "a" | "b",
  windowMinutes = 5
): Promise<number> {
  // Analytics Engine SQL API
  const query = `
    SELECT
      SUM(double2) AS errors,
      COUNT(*) AS total
    FROM ${env.ANALYTICS_DATASET}
    WHERE
      blob2 = 'outcome'
      AND blob4 = '${variant}'
      AND timestamp >= NOW() - INTERVAL '${windowMinutes}' MINUTE
  `;

  const response = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
    }
  );

  if (!response.ok) {
    throw new Error(`Analytics Engine query failed: ${response.status}`);
  }

  const data = await response.json<{
    data: Array<{ errors: number; total: number }>;
  }>();
  const row = data.data[0];
  if (!row || row.total === 0) return 0;
  return row.errors / row.total;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const threshold = parseFloat(env.ERROR_RATE_THRESHOLD);

    const [rateA, rateB] = await Promise.all([
      queryVariantErrorRate(env, "a"),
      queryVariantErrorRate(env, "b"),
    ]);

    console.log(`Error rates — A: ${(rateA * 100).toFixed(2)}%, B: ${(rateB * 100).toFixed(2)}%`);

    const current = await env.ROLLOUT_CONFIG.get("rollout", { type: "json" }) as { percentage: number } | null;
    if ((current?.percentage ?? 0) === 0) {
      // Already at 0%, nothing to roll back
      return;
    }

    if (rateB > threshold && rateB > rateA * 1.5) {
      // Variant B error rate exceeds threshold AND is 1.5x worse than A
      await env.ROLLOUT_CONFIG.put(
        "rollout",
        JSON.stringify({
          percentage: 0,
          updatedAt: new Date().toISOString(),
          updatedBy: "rollback-cron",
          reason: `variant_b_error_rate_${(rateB * 100).toFixed(2)}pct`,
        })
      );
      console.error(`AUTO-ROLLBACK: variant B error rate ${(rateB * 100).toFixed(2)}% > threshold ${(threshold * 100).toFixed(2)}%`);
    }
  },
};
```

```toml
# wrangler.toml — router Worker + rollback cron binding
name = "traffic-router"
main = "src/router.ts"
compatibility_date = "2026-08-01"

[[services]]
binding = "VARIANT_A"
service = "api-stable"

[[services]]
binding = "VARIANT_B"
service = "api-candidate"

[[kv_namespaces]]
binding = "ROLLOUT_CONFIG"
id = "rollout-config-kv-id"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "ab_experiments"

[vars]
ENVIRONMENT = "production"
ERROR_RATE_THRESHOLD = "0.05"

# Rollback cron — runs every 2 minutes
name = "rollback-cron"
main = "src/rollback-cron.ts"

[[rollback-cron.triggers]]
crons = ["*/2 * * * *"]
```

```typescript
// scripts/set-rollout.ts — CLI tool to adjust rollout percentage
import { execSync } from "child_process";

const percentage = parseInt(process.argv[2] ?? "0", 10);
if (percentage < 0 || percentage > 100) {
  console.error("Usage: ts-node set-rollout.ts <0-100>");
  process.exit(1);
}

const config = JSON.stringify({
  percentage,
  updatedAt: new Date().toISOString(),
  updatedBy: process.env.GITHUB_ACTOR ?? "manual",
});

execSync(
  `wrangler kv:key put --binding ROLLOUT_CONFIG rollout '${config}'`,
  { stdio: "inherit" }
);

console.log(`Rollout set to ${percentage}% for variant B.`);
```

## Implementation Details

**Gradual rollout playbook:**
```bash
# Deploy variant B alongside stable variant A
wrangler deploy --name api-candidate src/v2/index.ts

# Start at 5%
ts-node scripts/set-rollout.ts 5

# Monitor for 15 minutes, check Analytics Engine
# Increase to 25% if error rate is stable
ts-node scripts/set-rollout.ts 25

# Increase to 100% (full cutover)
ts-node scripts/set-rollout.ts 100

# After full cutover, rename api-candidate → api-stable
```

**Analytics Engine queries** — query variant performance via the CF API or Cloudflare dashboard:
```sql
-- Error rate per variant in last hour
SELECT
  blob4 AS variant,
  SUM(double2) / COUNT(*) AS error_rate,
  AVG(double1) AS avg_duration_ms,
  COUNT(*) AS total_requests
FROM ab_experiments
WHERE blob2 = 'outcome'
  AND timestamp >= NOW() - INTERVAL '1' HOUR
GROUP BY blob4
ORDER BY variant;

-- Conversion rate per variant
SELECT
  blob4 AS variant,
  SUM(double2) AS conversions,
  COUNT(*) AS total
FROM ab_experiments
WHERE blob2 = 'conversion'
  AND timestamp >= NOW() - INTERVAL '24' HOUR
GROUP BY blob4;
```

## Anti-patterns

- **Random routing instead of hash-based routing** — random means a user may see both variants in the same session, contaminating experiment results and confusing users.
- **Reading the rollout KV on every request without caching** — add `cacheTtl: 30` to `kv.get("rollout", { type: "json", cacheTtl: 30 })` to reduce KV reads; 30-second lag on rollout changes is acceptable.
- **Putting variant logic inside the main Worker** — keep the router Worker separate; it has no business logic, only routing logic, making it easy to reason about.
- **Routing based on IP alone** — IPs change (mobile users, VPNs, corporate NAT). Use a stable user ID or session cookie for deterministic assignment.
- **Auto-rollback without a minimum traffic threshold** — if traffic is near-zero, a single error makes the error rate 100%. Add a `total > 100` guard in the rollback cron before acting.

## Gotchas

- Service Bindings (`[[services]]`) only work within the same Cloudflare account. For cross-account A/B testing, use `fetch()` to the variant's `workers.dev` URL with an authentication header.
- Analytics Engine `writeDataPoint` is asynchronous and non-blocking; it does not affect response latency. However, data may lag up to 5 minutes in the SQL API.
- `AnalyticsEngineDataset` must be declared in both `wrangler.toml` AND in the Dashboard under Analytics Engine before it can accept data.
- FNV-1a hash collisions mean bucket distribution is approximately uniform but not perfectly uniform at low traffic — do not use for security-sensitive decisions.
- Variant B catching all errors and falling back to A masks B's failures in user-visible metrics but still logs them in Analytics Engine — monitor Analytics Engine, not just HTTP error rates.
- When `percentage = 100`, all traffic goes to variant B but the router Worker still adds latency. After full cutover, update the route to point directly to `api-candidate` and retire the router.

## Verification

```bash
# Set 10% rollout
ts-node scripts/set-rollout.ts 10

# Send 100 test requests, verify ~10 return X-Variant: b
for i in $(seq 1 100); do
  curl -s -o /dev/null -w "%{http_code} %header{x-variant}\n" \
    -H "Cookie: session=user-$i" \
    https://api.example.com/health
done | sort | uniq -c

# Query Analytics Engine for variant distribution
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{"query": "SELECT blob4, COUNT(*) FROM ab_experiments WHERE timestamp >= NOW() - INTERVAL 5 MINUTE GROUP BY blob4"}'

# Verify rollback cron is registered
wrangler triggers list --name rollback-cron
```

## Related

- `documentation/categories/infra/workers-wrangler-environments-matrix.md`
- `documentation/categories/infra/workers-multi-account-deployment.md`
- `documentation/categories/infra/workers-terraform-cloudflare-provider.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/kv/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
