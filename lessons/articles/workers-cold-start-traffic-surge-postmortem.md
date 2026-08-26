# Workers Cold Start Traffic Surge Postmortem

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A product launch triggered a 40x traffic spike over 90 seconds. Workers p99 latency climbed from ~18 ms to ~3.2 seconds during the initial surge. Error rate reached 8% (HTTP 524 — origin timeout). After roughly 4 minutes, latency returned to baseline. Post-incident analysis showed the spike was caused by thousands of simultaneous cold starts as Cloudflare's edge network provisioned new isolate instances across PoPs, not by any bug in the application code.

## Context

The Worker script had grown to 2.1 MB compressed due to accumulated SDKs (a telemetry client, a feature-flag SDK, a validation library). Top-level `await` calls initialized two D1 connections and fetched remote configuration from KV at module evaluation time. Every new isolate paid this initialization cost in full before serving its first request. During rapid scale-out, hundreds of isolates per PoP initialized simultaneously, each calling D1 and KV, which in turn increased latency on those services — compounding the problem. The team had no pre-warming strategy and had never load-tested cold-start behavior under burst traffic.

## 1. Measuring Cold-Start Contribution

Distinguish cold-start requests from warm requests using a startup timestamp:

```typescript
// Module-level flag set once per isolate lifetime
const isolateStartTime = Date.now();
let requestCount = 0;

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const isColdStart = requestCount === 0;
    requestCount++;

    const handlerStart = Date.now();
    const response = await handleRequest(request, env);
    const duration = Date.now() - handlerStart;

    // Emit cold-start flag to Analytics Engine for separate p50/p99 analysis
    env.ANALYTICS.writeDataPoint({
      blobs: [isColdStart ? "cold" : "warm", request.cf?.colo ?? "unknown"],
      doubles: [duration, Date.now() - isolateStartTime],
      indexes: ["request_latency"],
    });

    return response;
  },
};
```

Query to compare cold vs. warm p99:

```sql
SELECT
  blob1 AS start_type,
  quantileWeighted(0.50)(double1, 1) AS p50_ms,
  quantileWeighted(0.99)(double1, 1) AS p99_ms,
  count() AS requests
FROM request_latency
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY blob1
```

## 2. Eliminating Top-Level Await and Eager Initialization

Move initialization out of module scope and into lazy-init helpers:

```typescript
// BEFORE: initialization runs on every cold start, blocking the first request
import { createClient } from "@mycompany/feature-flags";
const flagClient = await createClient({ apiKey: env.FLAG_API_KEY }); // ← top-level await

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const flags = await flagClient.getFlags(request);
    // ...
  },
};
```

```typescript
// AFTER: lazy init — only pays cost on first request per isolate
let flagClient: FeatureFlagClient | null = null;

function getOrInitFlagClient(env: Env): FeatureFlagClient {
  if (!flagClient) {
    // Synchronous initialization only — no await at module scope
    flagClient = createClient({ apiKey: env.FLAG_API_KEY });
  }
  return flagClient;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const client = getOrInitFlagClient(env);
    const flags = await client.getFlags(request);
    // ...
  },
};
```

## 3. Reducing Script Bundle Size

Large bundles take longer to parse and JIT-compile on cold start. Profile and trim:

```bash
# Generate a bundle size report
npx wrangler deploy --dry-run --outdir dist 2>&1

# Inspect the output bundle
ls -lh dist/
npx esbuild-visualizer dist/worker.js --open
```

```typescript
// Replace heavy SDK imports with direct fetch calls where possible
// BEFORE: importing a 400 KB telemetry SDK
import { Honeybadger } from "@honeybadger-io/js"; // 400 KB

// AFTER: send telemetry directly with a 10-line helper
async function reportError(err: Error, ctx: { requestId: string }): Promise<void> {
  await fetch("https://api.honeybadger.io/v1/notices", {
    method: "POST",
    headers: {
      "X-API-Key": HONEYBADGER_API_KEY,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      notifier: { name: "workers-manual", version: "1.0.0" },
      error: { class: err.name, message: err.message, backtrace: [] },
      request: { context: ctx },
    }),
  });
}
```

## 4. Pre-Warming with a Cron Trigger

Use a lightweight Cron Trigger to keep isolates warm at high-traffic PoPs before a known launch:

```toml
# wrangler.toml
[[triggers]]
crons = ["*/1 * * * *"]  # every minute during launch window
```

```typescript
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    // Touch the D1 database and KV to initialize connections
    await env.DB.prepare("SELECT 1").run();
    const _ = await env.CONFIG.get("warmup");
    // Intentionally minimal — just enough to initialize the isolate
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    return handleRequest(request, env);
  },
};
```

Note: Cron Triggers do not guarantee isolate reuse — they fire in new isolates if existing ones have expired. This helps but is not a deterministic warm pool.

## 5. Enabling Smart Placement

Smart Placement routes Workers closer to their upstream data sources, reducing RTT to D1 and KV on cold starts:

```toml
# wrangler.toml
[placement]
mode = "smart"
```

```typescript
// Verify placement is working: compare colo in cf.colo vs. D1 location
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const colo = request.cf?.colo ?? "unknown";
    const t0 = performance.now();
    await env.DB.prepare("SELECT 1").run();
    const d1Latency = performance.now() - t0;

    // If d1Latency is consistently >20ms, Smart Placement may not be routing optimally
    return Response.json({ colo, d1Latency: d1Latency.toFixed(2) });
  },
};
```

## 6. Load-Testing Cold-Start Behavior

Add a surge load test to CI or pre-launch checklist that simulates cold-start conditions:

```typescript
// scripts/cold-start-loadtest.ts
// Uses a staggered burst to simulate many isolates initializing in parallel

const WORKER_URL = "https://myapp.example.workers.dev/healthz";
const CONCURRENCY = 200;
const RAMP_MS = 5000;

async function runBurst(): Promise<number[]> {
  const latencies: number[] = [];
  const promises = Array.from({ length: CONCURRENCY }, async (_, i) => {
    await new Promise((r) => setTimeout(r, (i / CONCURRENCY) * RAMP_MS));
    const t0 = performance.now();
    await fetch(WORKER_URL);
    latencies.push(performance.now() - t0);
  });
  await Promise.all(promises);
  return latencies;
}

const latencies = await runBurst();
latencies.sort((a, b) => a - b);
const p50 = latencies[Math.floor(latencies.length * 0.5)];
const p99 = latencies[Math.floor(latencies.length * 0.99)];
console.log(`Burst p50: ${p50.toFixed(0)}ms  p99: ${p99.toFixed(0)}ms`);

if (p99 > 2000) {
  console.error("Cold-start p99 exceeds 2s threshold — investigate before launch");
  process.exit(1);
}
```

## Anti-patterns

- Performing KV reads or D1 queries at module scope (top-level await). These block isolate initialization and add RTT to every cold start.
- Importing entire SDK packages when only one or two functions are used — use named imports and tree-shaking.
- Treating Workers as stateless Lambda functions with no warm-start behavior. Workers reuse isolates for many requests; write initialization code that runs once and is then cached in module scope.
- Measuring only warm-path latency in staging. A staging environment with low traffic always appears fast because isolates are warm.

## Gotchas

- Cloudflare does not guarantee any minimum isolate lifetime. An isolate can be evicted at any time, including mid-request. Do not store mutable state that must survive across requests in module scope (use Durable Objects instead).
- Smart Placement can increase cold-start latency in some topologies if it routes to a PoP that is geographically farther from the end user. Monitor both user-facing latency and upstream-call latency separately.
- Cron Triggers that warm isolates must be scheduled to the same geographic PoPs where traffic will arrive — this is not configurable; Cloudflare dispatches Cron Triggers from a limited set of PoPs.
- Workers with many imported modules (ESM) may parse slower than bundled single-file Workers. Prefer bundling for production.

## Verification

```bash
# Confirm script bundle size after optimization
npx wrangler deploy --dry-run 2>&1 | grep "Script size"

# Compare cold vs. warm latency percentiles in Analytics Engine
# (run the SQL query from section 1 after a deploy)

# Check Smart Placement routing
curl -s "https://myapp.example.workers.dev/debug/placement" | jq .
```

## Related

- workers-ai-cold-start-latency-production-lesson.md
- cache-cold-start-avalanche.md
- workers-smart-placement-latency-regression-postmortem.md
- workers-script-size-limit-exceeded.md

## Sources

- https://developers.cloudflare.com/workers/platform/limits/#worker-startup-time
- https://developers.cloudflare.com/workers/configuration/smart-placement/
- https://developers.cloudflare.com/workers/observability/logging/workers-logs/
- https://blog.cloudflare.com/workers-performance-isolates/
