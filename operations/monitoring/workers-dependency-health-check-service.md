# Downstream Dependency Health Check Service with Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your Worker calls several downstream services (databases, third-party APIs, internal microservices). You need a central health check service that probes each dependency on a schedule, distinguishes degraded from fully down, exposes an aggregated status endpoint, and renders a dependency dashboard — without spinning up dedicated infrastructure.

## Context

A cron-triggered Worker reads a dependency configuration list from KV, performs parallel HTTP health probes with per-dependency timeouts using `AbortController`, aggregates results, writes them back to KV, and exposes a query API. The dashboard endpoint renders an HTML dependency tree with color-coded status. The distinction between `degraded` (probe succeeded but latency > threshold) and `down` (probe failed or timed out) enables more nuanced alerting.

## Solution

### 1. Dependency configuration schema in KV

```typescript
// src/types/dependency.ts
export type HealthMethod = 'GET' | 'HEAD' | 'POST';
export type HealthStatus = 'healthy' | 'degraded' | 'down' | 'unknown';

export interface DependencyConfig {
  name: string;
  url: string;
  method: HealthMethod;
  timeoutMs: number;
  degradedThresholdMs: number;  // latency above this = degraded
  expectedStatus: number;       // expected HTTP status (e.g. 200)
  headers?: Record<string, string>;
  body?: string;                // for POST probes
  tags?: string[];              // grouping: ['database', 'external', 'critical']
  dependsOn?: string[];         // names of upstream dependencies in the tree
}

export interface HealthResult {
  name: string;
  url: string;
  status: HealthStatus;
  latencyMs: number;
  httpStatus?: number;
  error?: string;
  checkedAt: string;
}

// KV keys:
//   dep:config:list          -> string[]  (array of dependency names)
//   dep:config:{name}        -> DependencyConfig
//   dep:result:{name}        -> HealthResult
//   dep:history:{name}       -> HealthResult[]  (last 20 results)
```

### 2. Seeding dependency config into KV

```typescript
// scripts/seed-dependencies.ts  (run with wrangler kv:key put)
const dependencies: DependencyConfig[] = [
  {
    name: 'postgres-primary',
    url: 'https://db-proxy.internal/health',
    method: 'GET',
    timeoutMs: 3_000,
    degradedThresholdMs: 1_000,
    expectedStatus: 200,
    tags: ['database', 'critical'],
  },
  {
    name: 'stripe-api',
    url: 'https://api.stripe.com/v1',
    method: 'GET',
    timeoutMs: 5_000,
    degradedThresholdMs: 2_000,
    expectedStatus: 200,
    tags: ['external', 'payments'],
    dependsOn: [],
  },
  {
    name: 'auth-service',
    url: 'https://auth.internal/health',
    method: 'GET',
    timeoutMs: 2_000,
    degradedThresholdMs: 500,
    expectedStatus: 200,
    tags: ['internal', 'critical'],
    dependsOn: ['postgres-primary'],
  },
  {
    name: 'email-relay',
    url: 'https://api.sendgrid.com/v3/mail/send',
    method: 'HEAD',
    timeoutMs: 4_000,
    degradedThresholdMs: 2_000,
    expectedStatus: 405,  // HEAD returns 405 on this endpoint
    tags: ['external', 'notifications'],
  },
];

// Seed script output — pipe each to `wrangler kv:key put --namespace-id=XXX`
for (const dep of dependencies) {
  console.log(`dep:config:${dep.name}`, JSON.stringify(dep));
}
console.log('dep:config:list', JSON.stringify(dependencies.map((d) => d.name)));
```

### 3. Parallel health probe Worker

```typescript
// src/workers/dependency-health.ts
import { DependencyConfig, HealthResult, HealthStatus } from '../types/dependency';

interface Env {
  DEP_CONFIG: KVNamespace;
  ALERT_WEBHOOK_URL: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    const namesJson = await env.DEP_CONFIG.get('dep:config:list');
    if (!namesJson) {
      console.error('No dependency config list found in KV');
      return;
    }

    const names: string[] = JSON.parse(namesJson);
    const configs = await loadConfigs(env.DEP_CONFIG, names);

    // Run all probes in parallel
    const results = await Promise.all(configs.map((cfg) => probe(cfg)));

    // Persist results and history
    await Promise.all(
      results.map(async (result) => {
        await env.DEP_CONFIG.put(`dep:result:${result.name}`, JSON.stringify(result));

        const histKey = `dep:history:${result.name}`;
        const histJson = await env.DEP_CONFIG.get(histKey);
        const hist: HealthResult[] = histJson ? JSON.parse(histJson) : [];
        hist.unshift(result);
        if (hist.length > 20) hist.length = 20;
        await env.DEP_CONFIG.put(histKey, JSON.stringify(hist));
      })
    );

    // Alert on down/degraded
    const problems = results.filter((r) => r.status === 'down' || r.status === 'degraded');
    if (problems.length > 0) {
      const text = problems
        .map((r) => `${r.status.toUpperCase()} ${r.name} (${r.latencyMs}ms${r.error ? ': ' + r.error : ''})`)
        .join('\n');
      await fetch(env.ALERT_WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: `Dependency health issues:\n${text}` }),
      });
    }
  },
};

async function loadConfigs(kv: KVNamespace, names: string[]): Promise<DependencyConfig[]> {
  const configs = await Promise.all(
    names.map(async (name) => {
      const json = await kv.get(`dep:config:${name}`);
      return json ? (JSON.parse(json) as DependencyConfig) : null;
    })
  );
  return configs.filter((c): c is DependencyConfig => c !== null);
}

async function probe(cfg: DependencyConfig): Promise<HealthResult> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), cfg.timeoutMs);
  const start = Date.now();

  try {
    const res = await fetch(cfg.url, {
      method: cfg.method,
      headers: cfg.headers ?? {},
      body: cfg.body,
      signal: controller.signal,
    });
    const latencyMs = Date.now() - start;
    clearTimeout(timer);

    let status: HealthStatus;
    if (res.status !== cfg.expectedStatus) {
      status = 'down';
    } else if (latencyMs > cfg.degradedThresholdMs) {
      status = 'degraded';
    } else {
      status = 'healthy';
    }

    return { name: cfg.name, url: cfg.url, status, latencyMs, httpStatus: res.status, checkedAt: new Date().toISOString() };
  } catch (err) {
    clearTimeout(timer);
    const latencyMs = Date.now() - start;
    const isTimeout = (err as Error).name === 'AbortError';
    return {
      name: cfg.name,
      url: cfg.url,
      status: 'down',
      latencyMs,
      error: isTimeout ? `Timeout after ${cfg.timeoutMs}ms` : String(err),
      checkedAt: new Date().toISOString(),
    };
  }
}
```

### 4. Aggregated status API and dependency tree endpoint

```typescript
// src/workers/dependency-api.ts
import { Hono } from 'hono';
import { HealthResult, DependencyConfig, HealthStatus } from '../types/dependency';

interface Env { DEP_CONFIG: KVNamespace; }
const app = new Hono<{ Bindings: Env }>();

app.get('/health/dependencies', async (c) => {
  const namesJson = await c.env.DEP_CONFIG.get('dep:config:list');
  if (!namesJson) return c.json({ error: 'not configured' }, 503);
  const names: string[] = JSON.parse(namesJson);

  const results = await Promise.all(
    names.map(async (name) => {
      const json = await c.env.DEP_CONFIG.get(`dep:result:${name}`);
      return json ? (JSON.parse(json) as HealthResult) : null;
    })
  );
  const valid = results.filter((r): r is HealthResult => r !== null);

  const overall: HealthStatus =
    valid.some((r) => r.status === 'down') ? 'down' :
    valid.some((r) => r.status === 'degraded') ? 'degraded' : 'healthy';

  return c.json({ overall, dependencies: valid, checked_at: new Date().toISOString() });
});

app.get('/health/dependencies/tree', async (c) => {
  const namesJson = await c.env.DEP_CONFIG.get('dep:config:list');
  if (!namesJson) return c.json({ error: 'not configured' }, 503);
  const names: string[] = JSON.parse(namesJson);

  const [configs, results] = await Promise.all([
    Promise.all(names.map(async (n) => {
      const j = await c.env.DEP_CONFIG.get(`dep:config:${n}`);
      return j ? (JSON.parse(j) as DependencyConfig) : null;
    })),
    Promise.all(names.map(async (n) => {
      const j = await c.env.DEP_CONFIG.get(`dep:result:${n}`);
      return j ? (JSON.parse(j) as HealthResult) : null;
    })),
  ]);

  const cfgMap = new Map(configs.filter(Boolean).map((c) => [c!.name, c!]));
  const resMap = new Map(results.filter(Boolean).map((r) => [r!.name, r!]));

  // Build adjacency tree
  const nodes = names.map((name) => {
    const cfg = cfgMap.get(name);
    const res = resMap.get(name);
    return {
      name,
      status: res?.status ?? 'unknown',
      latencyMs: res?.latencyMs ?? 0,
      tags: cfg?.tags ?? [],
      dependsOn: cfg?.dependsOn ?? [],
      checkedAt: res?.checkedAt ?? null,
    };
  });

  return c.json({ nodes });
});

app.get('/health/dependencies/:name/history', async (c) => {
  const name = c.req.param('name');
  const json = await c.env.DEP_CONFIG.get(`dep:history:${name}`);
  if (!json) return c.json({ error: 'not found' }, 404);
  return c.json({ name, history: JSON.parse(json) });
});

export default app;
```

## Implementation Details

- **AbortController timeout**: Workers' `fetch()` ignores `{ signal }` if the request completes before the timer fires. Always `clearTimeout` in both success and error paths to avoid leaking timers.
- **Parallel probes**: `Promise.all` runs all probes concurrently. A single slow dependency does not block others because each has its own `AbortController` with an independent timeout.
- **Degraded vs down**: Degraded means the service answered correctly but slowly — appropriate for rate-limited warm-up or overloaded replicas. Down means the probe failed entirely. Route degraded to `warning` severity and down to `critical`.
- **KV history ring buffer**: Capping history at 20 entries per dependency limits KV value size. For richer history, write to Analytics Engine or D1.
- **`dependsOn` tree**: The tree structure is informational — it helps engineers understand blast radius (if `postgres-primary` is down, `auth-service` is expected to be down too). Do not suppress auth-service alerts automatically based on this.

## Anti-patterns

- **Sequential probes**: Probing dependencies one by one in a loop wastes execution time and may exhaust the Worker's CPU time limit for large dependency lists.
- **No timeout on probes**: Without `AbortController`, a slow downstream can block the Worker until the platform's 30-second subrequest timeout, delaying all other probes.
- **Storing full response bodies**: Only check status codes and latency. Reading and storing response bodies inflates KV value size and CPU cost.
- **Single health check endpoint per service**: Some services have different health endpoints per component (e.g. DB replica health vs primary). Model them as separate dependencies.

## Gotchas

- Workers' `fetch()` enforces a maximum of 6 concurrent subrequests in bundled mode. If you have more than 6 dependencies, they will queue internally rather than running truly concurrently — factor this into timeout math.
- KV `get` has eventual consistency. A result written in the previous cron run may not be visible for up to 60 seconds in rare cases. Avoid making real-time routing decisions based on KV health results.
- `HEAD` requests: some servers do not support `HEAD` and return 405. Either use `GET` or set `expectedStatus: 405` as shown in the Stripe example above.
- `AbortController` in Cloudflare Workers is the platform's native implementation. Do not import a polyfill — it is unnecessary and may conflict.

## Verification

1. Trigger the cron manually: `wrangler dev --test-scheduled`.
2. Check KV: `wrangler kv:key get dep:result:postgres-primary --namespace-id=XXX`.
3. Hit the API: `curl https://your-worker.workers.dev/health/dependencies | jq .overall`.
4. Intentionally misconfigure one dependency URL to return 404 and verify `status: "down"` in the next cron run.
5. Set `degradedThresholdMs: 1` for a fast dependency to simulate degraded state and verify alert fires.

## Related

- `workers-on-call-rotation-pagerduty` — route down/degraded alerts to PagerDuty
- `workers-uptime-monitor-cron-kv` — single-endpoint uptime monitoring
- `workers-synthetic-monitoring-playwright` — browser-level dependency verification
- `multi-environment-status-dashboard` — aggregate health across environments

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/fetch/#fetch-options
- https://developers.cloudflare.com/kv/api/read-key-value-pairs/
- https://developer.mozilla.org/en-US/docs/Web/API/AbortController
- https://developers.cloudflare.com/workers/platform/limits/#fetch-api
