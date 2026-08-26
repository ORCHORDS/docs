# A/B Test Deployment with Traffic Splitting via Workers + KV

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You want to run a controlled experiment where a percentage of users receives a new version of a feature (variant B) while the rest continue on the existing version (variant A). Assignment must be sticky across page loads so a single user always sees the same variant. You need conversion event tracking and a query endpoint to determine a winner before cleaning up the experiment.

## Context

Cloudflare Workers + KV enable edge-native A/B testing without any third-party experimentation platform. The experiment config lives in KV (editable without a re-deploy), assignment is stored in a first-party cookie, and conversion events are appended to a D1 table. Consistent hashing ensures the same anonymous user ID always lands in the same bucket even if the Worker restarts or a new PoP handles the request.

## Solution

### Experiment config schema in KV

Key: `experiment:<experiment-id>`

```typescript
// types/experiment.ts
export interface Variant {
  id: string;
  /** Weight as integer out of 100 */
  weight: number;
  /** Downstream service to route to, or null to use default */
  serviceBinding: string | null;
  /** Arbitrary metadata passed to the feature layer */
  meta: Record<string, unknown>;
}

export interface ExperimentConfig {
  id: string;
  name: string;
  /** 'running' | 'paused' | 'concluded' */
  status: 'running' | 'paused' | 'concluded';
  /** ISO-8601 */
  startedAt: string;
  concludedAt?: string;
  variants: Variant[];
  /** Conversion event name to track */
  conversionEvent: string;
}
```

Example KV value:

```json
{
  "id": "checkout-button-color",
  "name": "Checkout button color",
  "status": "running",
  "startedAt": "2026-08-24T00:00:00Z",
  "variants": [
    { "id": "control", "weight": 50, "serviceBinding": null, "meta": { "color": "blue" } },
    { "id": "treatment", "weight": 50, "serviceBinding": null, "meta": { "color": "green" } }
  ],
  "conversionEvent": "checkout_complete"
}
```

### Consistent bucket assignment

```typescript
// src/bucketing.ts

/**
 * Returns a stable bucket number [0, 99] for a given user+experiment pair.
 * Uses FNV-1a on the concatenated string for speed without SubtleCrypto.
 */
export function getBucket(userId: string, experimentId: string): number {
  const input = `${experimentId}:${userId}`;
  let hash = 2166136261; // FNV offset basis
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 16777619) >>> 0; // FNV prime, keep 32-bit
  }
  return hash % 100;
}

export function assignVariant(
  bucket: number,
  variants: { id: string; weight: number }[]
): string {
  let cumulative = 0;
  for (const variant of variants) {
    cumulative += variant.weight;
    if (bucket < cumulative) return variant.id;
  }
  // Fallback if weights don't sum to 100
  return variants[0].id;
}
```

### A/B Worker

```typescript
// src/index.ts
import { getBucket, assignVariant } from './bucketing';
import type { ExperimentConfig } from '../types/experiment';

export interface Env {
  EXPERIMENTS: KVNamespace;
  DB: D1Database;
  ORIGIN_CONTROL: Fetcher;
  ORIGIN_TREATMENT: Fetcher;
}

const EXPERIMENT_ID = 'checkout-button-color';
const ASSIGNMENT_COOKIE = 'ab_assignment';
const USER_COOKIE = 'user_id';

function getUserId(request: Request): string {
  const cookie = request.headers.get('Cookie') ?? '';
  const match = cookie.match(new RegExp(`(?:^|;\\s*)${USER_COOKIE}=([^;]+)`));
  if (match) return match[1];
  // Generate a new anonymous ID
  return crypto.randomUUID();
}

function getStoredAssignment(request: Request, expId: string): string | null {
  const cookie = request.headers.get('Cookie') ?? '';
  const key = `${ASSIGNMENT_COOKIE}_${expId}`;
  const match = cookie.match(new RegExp(`(?:^|;\\s*)${key}=([^;]+)`));
  return match ? match[1] : null;
}

function cookieHeader(name: string, value: string, maxAge = 60 * 60 * 24 * 30): string {
  return `${name}=${value}; Max-Age=${maxAge}; Path=/; SameSite=Lax; Secure`;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Conversion event recording endpoint
    if (request.method === 'POST' && url.pathname === '/__ab/convert') {
      const { experimentId, variantId, userId, event } =
        await request.json<{
          experimentId: string;
          variantId: string;
          userId: string;
          event: string;
        }>();
      await env.DB.prepare(
        `INSERT INTO ab_conversions (experiment_id, variant_id, user_id, event, converted_at)
         VALUES (?, ?, ?, ?, datetime('now'))`
      )
        .bind(experimentId, variantId, userId, event)
        .run();
      return new Response(null, { status: 204 });
    }

    // Experiment result query endpoint
    if (request.method === 'GET' && url.pathname === '/__ab/results') {
      const expId = url.searchParams.get('experiment') ?? EXPERIMENT_ID;
      const rows = await env.DB.prepare(
        `SELECT variant_id,
                COUNT(DISTINCT user_id)  AS unique_users,
                COUNT(*)                 AS conversions
         FROM ab_conversions
         WHERE experiment_id = ?
         GROUP BY variant_id`
      )
        .bind(expId)
        .all();
      return Response.json(rows.results);
    }

    // Load experiment config
    const config = await env.EXPERIMENTS.get<ExperimentConfig>(
      `experiment:${EXPERIMENT_ID}`,
      'json'
    );

    if (!config || config.status !== 'running') {
      return env.ORIGIN_CONTROL.fetch(request);
    }

    const userId = getUserId(request);
    const setCookies: string[] = [];

    // Re-use stored assignment for sticky bucketing
    let variantId = getStoredAssignment(request, config.id);
    if (!variantId) {
      const bucket = getBucket(userId, config.id);
      variantId = assignVariant(bucket, config.variants);
      setCookies.push(cookieHeader(`${ASSIGNMENT_COOKIE}_${config.id}`, variantId));
    }

    // Ensure user_id cookie persists
    const existingUserId = request.headers
      .get('Cookie')
      ?.match(new RegExp(`(?:^|;\\s*)${USER_COOKIE}=([^;]+)`));
    if (!existingUserId) {
      setCookies.push(cookieHeader(USER_COOKIE, userId));
    }

    // Route to the appropriate origin
    const variant = config.variants.find((v) => v.id === variantId)!;
    const origin =
      variantId === 'treatment' ? env.ORIGIN_TREATMENT : env.ORIGIN_CONTROL;

    // Inject experiment context for the origin Worker
    const upstreamRequest = new Request(request, {
      headers: new Headers({
        ...Object.fromEntries(request.headers),
        'X-AB-Experiment': config.id,
        'X-AB-Variant': variantId,
        'X-AB-Meta': JSON.stringify(variant.meta),
        'X-AB-User': userId,
      }),
    });

    const response = await origin.fetch(upstreamRequest);
    const mutableResponse = new Response(response.body, response);

    for (const cookie of setCookies) {
      mutableResponse.headers.append('Set-Cookie', cookie);
    }

    return mutableResponse;
  },
};
```

### D1 schema for conversions

```sql
-- migrations/0001_ab_conversions.sql
CREATE TABLE IF NOT EXISTS ab_conversions (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  experiment_id TEXT    NOT NULL,
  variant_id    TEXT    NOT NULL,
  user_id       TEXT    NOT NULL,
  event         TEXT    NOT NULL,
  converted_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_ab_exp_variant ON ab_conversions (experiment_id, variant_id);
CREATE UNIQUE INDEX idx_ab_user_event ON ab_conversions (experiment_id, user_id, event);
```

The unique index on `(experiment_id, user_id, event)` makes conversion recording idempotent.

### Winner declaration and cleanup

```bash
# Query results
curl "https://ab.orchords.workers.dev/__ab/results?experiment=checkout-button-color" \
  -H "X-Deploy-Secret: $SECRET" | jq .

# Declare winner: update status in KV
wrangler kv:key put "experiment:checkout-button-color" \
  "$(wrangler kv:key get "experiment:checkout-button-color" --namespace-id "$NS" | \
     jq '.status="concluded" | .concludedAt="2026-08-31T00:00:00Z"')" \
  --namespace-id "$NS" --env production

# After traffic fully migrated to winner, delete the experiment key
wrangler kv:key delete "experiment:checkout-button-color" --namespace-id "$NS" --env production
```

## Implementation Details

- FNV-1a hashing is chosen over `crypto.subtle` for bucket assignment because it is synchronous and runs in ~1 µs, adding no perceptible latency to the request path.
- The unique index on `ab_conversions` prevents double-counting if a client fires the conversion beacon twice (network retry).
- Assignment cookies use `SameSite=Lax` rather than `Strict` so users arriving from external links still carry their variant. Use `Strict` only if cross-site referrals are not a concern.
- The `X-AB-Meta` header lets downstream Workers access variant configuration (button colour, feature toggles) without making their own KV read.

## Anti-patterns

- **Re-assigning on every request.** If you call `getBucket` on every request without checking the stored cookie first, users will flip between variants on each load, invalidating the experiment.
- **Assigning based on IP address.** IP-to-user mapping is unreliable (NAT, VPNs). Always use a first-party cookie or authenticated user ID.
- **Weights that do not sum to 100.** The `assignVariant` function has a fallback, but verify weights sum to exactly 100 when writing the KV config; silent rounding errors skew results.
- **Keeping experiments running indefinitely.** Concluded experiments accumulate assignment cookies in browsers. Set `concludedAt`, route 100% to the winner, then delete the KV key within one cookie `Max-Age` period.

## Gotchas

- KV reads in the hot path add ~1–5 ms of latency at the edge. Cache the config in-memory for 30 s (similar to the maintenance window pattern) to keep p99 latency low.
- `Math.imul` performs C-like 32-bit integer multiplication in JavaScript. Without `>>> 0` the result may become a signed negative integer, producing a negative modulo on some JS engines. The `>>> 0` cast keeps it unsigned.
- `new Request(request, { headers: ... })` on a request with a body will tee the body. If the origin reads the body, ensure the teed stream is not already consumed.
- D1 unique constraint violations return a `SQLITE_CONSTRAINT_UNIQUE` error code. Wrap the insert in a try/catch and treat constraint violations as a 204 (idempotent success) rather than a 500.

## Verification

1. Set experiment status to `running` in KV with 50/50 weights.
2. Send 1 000 requests with varying `user_id` cookies; count `X-AB-Variant` headers in responses — confirm ~500 each.
3. Fire 10 conversion events for each variant; query `/results` and confirm counts match.
4. Verify a subsequent request from the same `user_id` always returns the same variant (sticky assignment).
5. Set experiment status to `concluded`; confirm 100% of traffic routes to `ORIGIN_CONTROL` (or whichever is the default).

## Related

- `workers-feature-flag-deployment-kv.md`
- `canary-deployment-kv-flag.md`
- `workers-gradual-traffic-migration-routes.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/d1/
- https://en.wikipedia.org/wiki/Fowler%E2%80%93Noll%E2%80%93Vo_hash_function
