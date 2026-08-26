# Graceful Degradation with Feature Tiers in Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

An upstream AI provider goes down. D1 query latency spikes to 5 seconds. A third-party enrichment API starts returning 503s. Without a degradation strategy the entire product goes dark, even though the core use-case (serving cached content) is fully available. You need a way to automatically downgrade behaviour to what is available, log the transition, and recover when conditions improve — without a deployment.

## Context

Graceful degradation means a system continues to operate at reduced capability rather than failing entirely when a dependency is unavailable. Feature tiers formalise this: instead of binary up/down, the system has named capability levels (e.g., `full`, `reduced`, `minimal`) and a mechanism to switch between them.

Cloudflare KV is ideal for tier configuration: reads are globally fast (edge cache), writes propagate in seconds, and the Worker can read the current tier on every request without a D1 round-trip. The pattern:

1. A KV key holds the current tier config per tenant (or globally).
2. Each request reads the tier, selects the appropriate code path.
3. A health-check Cron Worker periodically probes upstreams and writes tier transitions to KV.
4. Tier transitions are logged for post-incident review.
5. Recovery to full tier happens automatically when upstreams pass health checks.

## Solution

### 1. Tier Configuration Schema in KV

```typescript
// types/tiers.ts
export type TierLevel = 'full' | 'reduced' | 'minimal';

export interface TierConfig {
  level: TierLevel;
  reason: string;
  since: number;    // epoch ms
  autoRecover: boolean;
}

export const DEFAULT_TIER: TierConfig = {
  level: 'full',
  reason: 'nominal',
  since: 0,
  autoRecover: true,
};

// What each tier enables
export const TIER_CAPABILITIES: Record<TierLevel, {
  aiEnabled: boolean;
  d1Enabled: boolean;
  enrichmentEnabled: boolean;
  cacheOnly: boolean;
}> = {
  full: {
    aiEnabled: true,
    d1Enabled: true,
    enrichmentEnabled: true,
    cacheOnly: false,
  },
  reduced: {
    aiEnabled: false,   // AI provider degraded
    d1Enabled: true,
    enrichmentEnabled: false,
    cacheOnly: false,
  },
  minimal: {
    aiEnabled: false,
    d1Enabled: false,
    enrichmentEnabled: false,
    cacheOnly: true,   // serve KV cache only
  },
};
```

### 2. Tier Reader — cached with a local in-process TTL

```typescript
// lib/tier.ts
import { TierConfig, DEFAULT_TIER, TIER_CAPABILITIES } from '../types/tiers';

const TIER_KV_KEY = 'system:tier';
const LOCAL_CACHE_TTL_MS = 5_000; // Re-read KV at most every 5 seconds

// Module-level cache (lives for the lifetime of the Worker isolate)
let cachedTier: TierConfig = DEFAULT_TIER;
let cacheAt = 0;

export async function getTier(kv: KVNamespace): Promise<TierConfig> {
  const now = Date.now();
  if (now - cacheAt < LOCAL_CACHE_TTL_MS) return cachedTier;

  const stored = await kv.get<TierConfig>(TIER_KV_KEY, 'json');
  cachedTier = stored ?? DEFAULT_TIER;
  cacheAt = now;
  return cachedTier;
}

export function getCapabilities(tier: TierConfig) {
  return TIER_CAPABILITIES[tier.level];
}

export async function setTier(
  kv: KVNamespace,
  level: TierConfig['level'],
  reason: string
): Promise<TierConfig> {
  const config: TierConfig = { level, reason, since: Date.now(), autoRecover: true };
  await kv.put(TIER_KV_KEY, JSON.stringify(config));
  // Invalidate local cache immediately
  cachedTier = config;
  cacheAt = Date.now();
  return config;
}
```

### 3. Primary Worker — tier-aware request handler

```typescript
// worker.ts
import { getTier, getCapabilities } from './lib/tier';
import { TierConfig } from './types/tiers';

export interface Env {
  TIER_KV:   KVNamespace;
  CACHE_KV:  KVNamespace;
  DB:        D1Database;
  AI:        Ai;
  LOG_QUEUE: Queue;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const tier = await getTier(env.TIER_KV);
    const caps = getCapabilities(tier);
    const url  = new URL(request.url);

    // Add tier info to every response for observability
    const tierHeaders = {
      'X-Feature-Tier': tier.level,
      'X-Tier-Reason':  tier.reason,
    };

    // Minimal tier: serve from KV cache only
    if (caps.cacheOnly) {
      const cached = await env.CACHE_KV.get(url.pathname, 'text');
      if (cached) {
        return new Response(cached, {
          status: 200,
          headers: { 'Content-Type': 'application/json', ...tierHeaders },
        });
      }
      return new Response(
        JSON.stringify({ error: 'Service degraded — cached data unavailable for this resource' }),
        { status: 503, headers: { 'Content-Type': 'application/json', ...tierHeaders } }
      );
    }

    // Reduced / full tier: query D1
    const dbStart = Date.now();
    const { results } = await env.DB.prepare(
      'SELECT id, name, summary FROM products WHERE active = 1 LIMIT 50'
    ).all<{ id: string; name: string; summary: string }>();
    const dbMs = Date.now() - dbStart;

    // If D1 is responding slowly, transition to minimal (async — does not block response)
    if (dbMs > 3000) {
      ctx.waitUntil(transitionTier(env, 'minimal', `D1 latency ${dbMs}ms`));
    }

    let enriched = results;

    // Full tier only: enrich with AI summaries
    if (caps.aiEnabled) {
      try {
        enriched = await enrichWithAI(results, env.AI);
      } catch (err) {
        // AI failed — transition to reduced tier (async)
        ctx.waitUntil(transitionTier(env, 'reduced', `AI error: ${(err as Error).message}`));
        // Continue with un-enriched data
      }
    }

    // Cache the result for minimal-tier fallback
    ctx.waitUntil(
      env.CACHE_KV.put(url.pathname, JSON.stringify(enriched), { expirationTtl: 300 })
    );

    return Response.json(enriched, { headers: tierHeaders });
  },
};

async function enrichWithAI(
  items: { id: string; name: string; summary: string }[],
  ai: Ai
): Promise<{ id: string; name: string; summary: string; aiTag?: string }[]> {
  const result = await ai.run('@cf/meta/llama-3-8b-instruct', {
    messages: [{
      role: 'user',
      content: `Tag each product with one word. Products: ${items.map((i) => i.name).join(', ')}`,
    }],
  }) as { response: string };

  const tags = result.response.split(',').map((t) => t.trim());
  return items.map((item, i) => ({ ...item, aiTag: tags[i] }));
}

async function transitionTier(env: Env, level: 'reduced' | 'minimal', reason: string) {
  const { setTier } = await import('./lib/tier');
  const config = await setTier(env.TIER_KV, level, reason);
  // Async log via queue
  await env.LOG_QUEUE.send({
    type: 'tier_transition',
    level: config.level,
    reason: config.reason,
    since: config.since,
  }).catch(() => {});
}
```

### 4. Health-Check Cron — automatic tier transitions and recovery

```typescript
// health-worker.ts
import { getTier, setTier } from './lib/tier';

export interface HealthEnv {
  TIER_KV:       KVNamespace;
  LOG_QUEUE:     Queue;
  DB:            D1Database;
  AI_PROBE_URL:  string; // Secret — e.g. https://api.example.com/ai/ping
  AI_PROBE_TOKEN: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: HealthEnv, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runHealthCheck(env));
  },
};

async function runHealthCheck(env: HealthEnv): Promise<void> {
  const current = await getTier(env.TIER_KV);
  const results = await Promise.allSettled([
    probeD1(env.DB),
    probeAI(env.AI_PROBE_URL, env.AI_PROBE_TOKEN),
  ]);

  const d1Ok  = results[0].status === 'fulfilled' && results[0].value;
  const aiOk  = results[1].status === 'fulfilled' && results[1].value;

  let targetLevel: 'full' | 'reduced' | 'minimal';
  let reason: string;

  if (!d1Ok) {
    targetLevel = 'minimal';
    reason = 'D1 health check failed';
  } else if (!aiOk) {
    targetLevel = 'reduced';
    reason = 'AI health check failed';
  } else {
    targetLevel = 'full';
    reason = 'All upstreams healthy';
  }

  // Only write if tier changed — avoid KV write storms
  if (targetLevel !== current.level) {
    const next = await setTier(env.TIER_KV, targetLevel, reason);
    await env.LOG_QUEUE.send({
      type: 'tier_transition',
      from: current.level,
      to:   next.level,
      reason,
      ts:   new Date().toISOString(),
    }).catch(() => {});
    console.log(`Tier transition: ${current.level} → ${next.level} (${reason})`);
  }
}

async function probeD1(db: D1Database): Promise<boolean> {
  try {
    const start = Date.now();
    await db.prepare('SELECT 1').run();
    const ms = Date.now() - start;
    return ms < 2000; // Treat slow D1 as unhealthy
  } catch {
    return false;
  }
}

async function probeAI(url: string, token: string): Promise<boolean> {
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 5000);
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    return res.ok;
  } catch {
    return false;
  }
}
```

```toml
# health-worker/wrangler.toml
name = "health-worker"
[triggers]
crons = ["* * * * *"]  # every minute
```

### 5. Tier Transition Log Consumer (Queue)

```typescript
// log-consumer-worker.ts
export default {
  async queue(batch: MessageBatch, _env: unknown): Promise<void> {
    for (const msg of batch.messages) {
      const body = msg.body as Record<string, unknown>;
      if (body.type === 'tier_transition') {
        // Forward to observability platform (Datadog, Better Uptime, etc.)
        console.log('[TIER]', JSON.stringify(body));
      }
      msg.ack();
    }
  },
};
```

## Implementation Details

- **KV as control plane**: KV reads at the edge are cached for up to 60 seconds by default. Use the `cacheTtl` option on `kv.get()` and supplement with a short in-process TTL (5 s) so tier changes propagate quickly without hammering KV.
- **Tier propagation lag**: After `kv.put()`, edge caches may serve the old tier for up to 60 seconds. Design the system to tolerate this: a `reduced` Worker briefly serving `full` requests is safe; the reverse is not. Always degrade conservatively.
- **Async transitions**: Never block the response to write a tier transition — use `ctx.waitUntil()`. The current request should complete at whatever tier it started.
- **Idempotent cron**: The health-check cron only writes to KV when the tier changes. This prevents write-amplification if the cron fires every minute.
- **Manual override**: Add an admin endpoint to force a tier level. Protect it with a separate admin API key stored as a Worker secret.

## Anti-patterns

- **Binary up/down only**: A single feature flag is insufficient. Granular tiers allow serving most users unaffected when one upstream degrades.
- **Degrading in the hot path synchronously**: Writing tier transitions during request handling adds latency. Use `waitUntil` or let the health-check cron handle it.
- **Caching stale KV in memory forever**: Module-level caches survive for the lifetime of the isolate (minutes to hours). Always set a short TTL — 5 seconds is a safe default.
- **Not testing the minimal tier**: Minimal-tier paths are often untested and broken exactly when they are needed most. Add integration tests that force the tier and hit all endpoints.
- **Tier config in wrangler.toml vars**: Hardcoded vars require a redeployment to change. KV enables runtime tier switching in seconds.

## Gotchas

- KV write propagation is eventually consistent — up to 60 s globally. In multi-region scenarios a Worker in one region may read an old tier while one in another sees the new tier. Design for this window.
- Module-level variables (the local cache) are shared across all requests handled by the same isolate but are NOT shared across isolates. Each isolate independently reads KV until its local cache warms.
- The `AI` binding (Workers AI) does not support `AbortController` — if the model times out, your Worker request will time out. Wrap AI calls in a `Promise.race()` with a manual timeout using `setTimeout` + rejection.
- Health-check crons fire once per minute minimum. For faster recovery, supplement with the inline latency check in the primary Worker (`if (dbMs > 3000)`).
- Do not use `wrangler.toml` `[vars]` for tier config — it is not writable at runtime. KV is the correct store.

## Verification

```bash
# Read current tier
npx wrangler kv key get --namespace-id=<TIER_KV_ID> "system:tier"

# Force reduced tier
npx wrangler kv key put --namespace-id=<TIER_KV_ID> "system:tier" \
  '{"level":"reduced","reason":"manual test","since":0,"autoRecover":true}'

# Hit primary Worker — verify X-Feature-Tier header
curl -si https://my-worker.example.workers.dev/products | grep X-Feature-Tier
# Expected: X-Feature-Tier: reduced

# Force minimal tier and verify cache-only response
npx wrangler kv key put --namespace-id=<TIER_KV_ID> "system:tier" \
  '{"level":"minimal","reason":"manual test","since":0,"autoRecover":true}'
curl -si https://my-worker.example.workers.dev/products
# Expected: 200 from cache OR 503 if cache empty — never a D1 call

# Restore full tier
npx wrangler kv key put --namespace-id=<TIER_KV_ID> "system:tier" \
  '{"level":"full","reason":"recovered","since":0,"autoRecover":true}'
```

## Related

- `workers-sidecar-pattern-service-binding.md`
- `workers-lambda-architecture-batch-stream.md`
- `anti-corruption-layer-legacy.md`
- `workers-strangler-fig-migration-pattern.md`

## Sources

- Nygard, M. (2018). *Release It!* 2nd ed. Pragmatic Programmers. Chapter 4: Stability Patterns.
- Fowler, M. "Graceful Degradation". martinfowler.com.
- Cloudflare KV: https://developers.cloudflare.com/kv/
- Cloudflare Workers AI: https://developers.cloudflare.com/workers-ai/
- Cloudflare Queues: https://developers.cloudflare.com/queues/
