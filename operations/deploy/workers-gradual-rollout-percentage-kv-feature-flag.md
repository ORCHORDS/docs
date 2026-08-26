# Gradual Percentage Rollout for Workers Using KV Feature Flags

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to expose a new Workers feature to a growing percentage of users — starting at 1%, ramping to 100% — ensuring the same user always gets the same variant (sticky assignment), with the ability to adjust or kill the rollout instantly via a KV write.

## Context

A KV-backed feature flag system lets you control rollout percentages without redeployment. A deterministic hash of the user identifier maps each user to a stable bucket (0–99). If the bucket is below the stored percentage the user is in the treatment group; otherwise they see the control. The percentage is stored at `rollout:<feature>` in KV and is readable by any Worker bound to the same namespace.

Components:
- `rolloutPercent()` — deterministic hash function
- KV namespace `FEATURE_FLAGS` storing `rollout:<feature>` (0–100)
- Management endpoint to update percentages (admin-token protected)
- Analytics Engine logging for variant assignments
- Circuit breaker that zeros the rollout on error-rate spike

## Core rollout logic and management Worker

```typescript
// src/index.ts
import type { Env } from './env';

export interface Env {
  FEATURE_FLAGS: KVNamespace;
  ANALYTICS: AnalyticsEngineDataset;
  ADMIN_TOKEN: string;
}

// djb2 hash → stable 0–99 bucket for a given user+feature key
function djb2(str: string): number {
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash) ^ str.charCodeAt(i);
    hash = hash >>> 0; // keep unsigned 32-bit
  }
  return hash % 100;
}

export async function rolloutPercent(
  feature: string,
  userId: string,
  env: Env
): Promise<'treatment' | 'control'> {
  const raw = await env.FEATURE_FLAGS.get(`rollout:${feature}`);
  const percent = raw !== null ? Math.min(100, Math.max(0, parseInt(raw, 10))) : 0;

  if (percent === 0) return 'control';
  if (percent === 100) return 'treatment';

  const bucket = djb2(`${feature}:${userId}`);
  return bucket < percent ? 'treatment' : 'control';
}

// Log assignment to Analytics Engine
function logAssignment(
  env: Env,
  feature: string,
  userId: string,
  variant: string
): void {
  env.ANALYTICS.writeDataPoint({
    blobs: [feature, userId, variant],
    doubles: [Date.now()],
    indexes: [feature],
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // ── Management endpoint ──────────────────────────────────────────────────
    if (url.pathname.startsWith('/admin/rollout')) {
      const authHeader = request.headers.get('Authorization') ?? '';
      if (authHeader !== `Bearer ${env.ADMIN_TOKEN}`) {
        return new Response('Unauthorized', { status: 401 });
      }

      if (request.method === 'PUT') {
        const { feature, percent } = await request.json() as { feature: string; percent: number };
        if (typeof feature !== 'string' || typeof percent !== 'number' || percent < 0 || percent > 100) {
          return new Response('Invalid payload', { status: 400 });
        }
        await env.FEATURE_FLAGS.put(`rollout:${feature}`, String(percent));
        return Response.json({ ok: true, feature, percent });
      }

      if (request.method === 'GET') {
        const feature = url.searchParams.get('feature');
        if (!feature) return new Response('Missing feature param', { status: 400 });
        const value = await env.FEATURE_FLAGS.get(`rollout:${feature}`);
        return Response.json({ feature, percent: value !== null ? parseInt(value) : 0 });
      }

      return new Response('Method not allowed', { status: 405 });
    }

    // ── Application logic ────────────────────────────────────────────────────
    const userId = request.headers.get('CF-Connecting-IP') ?? 'anonymous';
    const feature = 'new-checkout';

    let variant: 'treatment' | 'control';
    try {
      variant = await rolloutPercent(feature, userId, env);
    } catch (err) {
      // Circuit breaker: on unexpected error default to control
      console.error('rolloutPercent error:', err);
      variant = 'control';
    }

    logAssignment(env, feature, userId, variant);

    return Response.json({ variant, userId });
  },
};
```

## wrangler.toml

```toml
name = "rollout-worker"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[[kv_namespaces]]
binding = "FEATURE_FLAGS"
id = "<your-kv-namespace-id>"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "rollout_assignments"

[vars]
ADMIN_TOKEN = "replace-with-secret"
```

## Updating rollout percentage via management endpoint

```bash
# Ramp feature to 20%
curl -X PUT https://rollout-worker.example.workers.dev/admin/rollout \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"feature": "new-checkout", "percent": 20}'

# Circuit-breaker kill switch — zero it out instantly
curl -X PUT https://rollout-worker.example.workers.dev/admin/rollout \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"feature": "new-checkout", "percent": 0}'
```

## Circuit breaker — auto-zero on error-rate spike

```typescript
// scripts/circuit-breaker.ts  (run from a Durable Object alarm or external cron)
export async function checkAndBreak(
  feature: string,
  errorRate: number,   // 0.0–1.0, computed from Analytics Engine query
  threshold: number,   // e.g. 0.05 for 5%
  env: Env
): Promise<void> {
  if (errorRate > threshold) {
    console.warn(`Error rate ${errorRate} exceeds threshold ${threshold} — zeroing rollout for ${feature}`);
    await env.FEATURE_FLAGS.put(`rollout:${feature}`, '0');
  }
}
```

## Anti-patterns

- **Using `Math.random()` for bucket assignment** — not deterministic; the same user will flip between variants on every request.
- **Storing user-to-variant mapping in KV** — does not scale; derive the bucket from the hash instead.
- **Exposing the management endpoint without auth** — any caller could change rollout percentages; always validate the admin token.
- **Ignoring KV read latency in the hot path** — cache the percentage value with a short TTL using `cacheTtl` option: `env.FEATURE_FLAGS.get(key, { cacheTtl: 60 })`.

## Gotchas

- `djb2` is not cryptographically secure. For sensitive experiments use a HMAC-based bucket instead.
- KV `get` with `cacheTtl` means a percentage change takes up to that many seconds to propagate globally — keep TTL low (30–60 s) for kill-switch responsiveness.
- Analytics Engine data points are batched; there may be a short delay before assignments appear in SQL queries.
- `parseInt` on a non-numeric KV value returns `NaN` — the `Math.max(0, ...)` guard clamps it to 0 (safe control fallback).

## Verification

```bash
# Check current rollout percentage
curl "https://rollout-worker.example.workers.dev/admin/rollout?feature=new-checkout" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Query Analytics Engine for assignment distribution
wrangler analytics-engine query \
  --dataset rollout_assignments \
  --sql "SELECT blob3 AS variant, count() AS n FROM rollout_assignments GROUP BY variant"
```

## Related

- `workers-blue-green-deploy-traffic-split-kv.md`
- `workers-deployment-annotations-version-tags.md`
- `wrangler-environments-staging-prod-promotion.md`

## Sources

- Cloudflare KV: https://developers.cloudflare.com/kv/
- Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Feature flag patterns: https://martinfowler.com/articles/feature-toggles.html
