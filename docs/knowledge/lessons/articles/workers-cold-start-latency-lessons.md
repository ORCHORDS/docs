# Workers Cold Start Latency — Lessons Learned

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Our API gateway Worker occasionally responded in 800 ms where the p50 was 12 ms. The outliers were
random, correlated with idle periods, and disappeared on the second request to the same isolate.
Customers on the free tier (no Durable Objects, no Smart Placement) were affected most. We spent
two sprints chasing the wrong things before we understood what actually moves the needle.

---

## Context

Cloudflare Workers execute inside V8 *isolates* — lightweight, single-threaded JavaScript contexts
that are cheaper than Node.js processes but still have a boot cost. A **cold start** occurs when
the runtime has no warm isolate available for your Worker. Costs include:

1. Spinning up a new V8 isolate
2. Parsing and compiling your bundled JS (or running the Wasm instantiation)
3. Executing top-level module code (imports, class definitions, `const` initialisations)
4. Running your `fetch` handler for the first time

Cloudflare does not expose a raw "cold start" metric; you infer it from the p99–p50 gap.

---

## Solution

### 1. Minimise bundle size — the single highest-leverage action

Every byte of JS the runtime has to parse costs CPU time during a cold start. We went from a
420 kB bundle to 87 kB and cut our p99 by ~65 %.

Measure first:

```bash
npx wrangler deploy --dry-run --outdir dist/
# inspect dist/*.js size
npx bundle-buddy dist/*.js   # optional visual breakdown
```

Tree-shake ruthlessly in `wrangler.toml`:

```toml
[build]
command = "npm run build"

[build.upload]
format = "modules"   # ESM modules tree-shake better than CJS
```

```typescript
// tsconfig.json — ensure ESM output
{
  "compilerOptions": {
    "module": "ESNext",
    "moduleResolution": "bundler",
    "target": "ESNext"
  }
}
```

Replace heavy SDK imports with hand-rolled fetch calls:

```typescript
// BEFORE — pulls in 180 kB of AWS SDK
import { DynamoDBClient, GetItemCommand } from '@aws-sdk/client-dynamodb';

// AFTER — 23 lines, same effect
async function dynamoGet(
  table: string,
  key: Record<string, { S: string }>,
  env: { AWS_ACCESS_KEY_ID: string; AWS_SECRET_ACCESS_KEY: string; AWS_REGION: string }
): Promise<Record<string, unknown> | null> {
  const url = `https://dynamodb.${env.AWS_REGION}.amazonaws.com/`;
  const body = JSON.stringify({
    TableName: table,
    Key: key,
  });

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-amz-json-1.0',
      'X-Amz-Target': 'DynamoDB_20120810.GetItem',
      // sign with a lightweight HMAC helper (< 2 kB)
    },
    body,
  });

  const data = (await resp.json()) as { Item?: Record<string, unknown> };
  return data.Item ?? null;
}
```

### 2. Move expensive work to module-level — but cautiously

Module-level code runs once per isolate lifetime, not once per request:

```typescript
// Good: parse config once, reuse across requests
const ROUTES = new Map([
  ['/health', handleHealth],
  ['/api/v1/orders', handleOrders],
]);

// Good: compile regex once
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const handler = ROUTES.get(url.pathname);
    if (!handler) return new Response('Not found', { status: 404 });
    return handler(request);
  },
};
```

Avoid module-level **I/O** — it will block every cold start:

```typescript
// BAD — awaits a KV read at module load time, blocks isolate startup
const config = await CONFIG_KV.get('app-config', 'json');

// GOOD — lazy-load with a module-level promise
let configPromise: Promise<AppConfig> | null = null;

function getConfig(kv: KVNamespace): Promise<AppConfig> {
  if (!configPromise) {
    configPromise = kv.get<AppConfig>('app-config', 'json').then((v) => {
      if (!v) throw new Error('Missing config');
      return v;
    });
  }
  return configPromise;
}
```

### 3. Avoid dynamic `import()` inside the hot path

Dynamic imports trigger additional module evaluation cost. In Workers they do NOT split the bundle
into lazy chunks the way webpack does in a browser — the entire bundle is still uploaded as one
file. You pay the parsing cost upfront regardless, but the dynamic `import()` call still adds
runtime overhead.

```typescript
// BAD — dynamic import on every PDF request
export default {
  async fetch(request: Request): Promise<Response> {
    if (request.url.endsWith('/pdf')) {
      const { render } = await import('./pdf-renderer');  // overhead every time
      return render(request);
    }
    return new Response('ok');
  },
};

// GOOD — static import, tree-shaker removes it if unused
import { render } from './pdf-renderer';

export default {
  async fetch(request: Request): Promise<Response> {
    if (request.url.endsWith('/pdf')) return render(request);
    return new Response('ok');
  },
};
```

### 4. Enable Smart Placement (if eligible)

Smart Placement moves your Worker closer to back-end services rather than the user, reducing the
number of isolate instantiations in distant PoPs.

```toml
# wrangler.toml
[placement]
mode = "smart"
```

This helped our DB-heavy Workers significantly (p99 down 30 %) but had zero effect on our
edge-cache Workers that did no egress I/O.

---

## Implementation Details

### Measuring cold start contribution

```typescript
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const startMs = Date.now();

    // A module-level flag flips from false → true after the first request.
    // If it is still false this is the first invocation on this isolate.
    const isColdStart = !isolateWarmed;
    isolateWarmed = true;

    const response = await handleRequest(request, env);

    // Emit to Analytics Engine
    env.ANALYTICS.writeDataPoint({
      blobs: [new URL(request.url).pathname],
      doubles: [Date.now() - startMs],
      indexes: [isColdStart ? 'cold' : 'warm'],
    });

    return response;
  },
};

let isolateWarmed = false;
```

### CPU time budget

Workers have a CPU-time limit (50 ms on the free tier, 30 s on paid). Cold-start module
initialisation counts against this budget. A 2 MB bundle can easily consume 15–20 ms of CPU just
in parsing.

```typescript
// Approximate your parse budget with a build-time check
// Add to package.json scripts:
// "check:bundle": "node scripts/check-bundle-size.mjs"

// scripts/check-bundle-size.mjs
import { statSync } from 'fs';
const { size } = statSync('dist/worker.js');
const KB = size / 1024;
console.log(`Bundle: ${KB.toFixed(1)} kB`);
if (KB > 200) {
  console.error('ERROR: bundle exceeds 200 kB target');
  process.exit(1);
}
```

---

## Anti-patterns

| Anti-pattern | Reality |
|---|---|
| "Keep-alive" pings to prevent cold starts | Cloudflare evicts isolates on their own schedule; you cannot pin one with traffic |
| Splitting into many small Workers to reduce bundle size | Each Worker has its own cold-start; more Workers = more cold surfaces |
| Preloading everything at module level | Top-level `await` is allowed but any I/O there blocks the cold-start itself |
| Using Node.js-compatible mode unnecessarily | Node compat shims add ~30 kB and extra init cost; only enable what you need |
| Assuming Wasm is always faster | Wasm instantiation has its own cost; tiny functions are faster in plain JS |

---

## Gotchas

1. **Cloudflare does not guarantee isolate reuse.** Even a Worker serving 10 k req/s may
   occasionally cold-start because a PoP spins up a new isolate to absorb a traffic spike.

2. **`waitUntil()` does NOT keep an isolate alive** for future requests — it only extends the
   current isolate's lifetime until the background task completes.

3. **The CPU-time clock ticks during `await`** for D1 and Workers AI, but NOT during `fetch()` to
   external origins. Plan accordingly.

4. **esbuild's `--minify` flag** reduces bundle size but not parse time proportionally — the
   runtime still parses every token. `--minify-syntax` (constant folding) is more effective than
   `--minify-whitespace` alone.

5. **Module-level `console.log`** is silently dropped in production builds but still costs a tiny
   amount of parse time if left in source. Strip it with a build plugin.

---

## Verification

Check p50 vs p99 in Workers Analytics or Logpush:

```sql
-- Workers Analytics Engine query (GraphQL)
{
  viewer {
    zones(filter: { zoneTag: $zoneTag }) {
      workersInvocationsAdaptive(
        filter: { datetime_geq: "2026-08-01T00:00:00Z" }
        orderBy: [sum_requests_DESC]
        limit: 10
      ) {
        dimensions { scriptName }
        sum { requests }
        quantiles { cpuTimeP50 cpuTimeP99 }
      }
    }
  }
}
```

A healthy Worker has `cpuTimeP99 / cpuTimeP50 < 3`. Ratios above 10 indicate cold-start spikes.

---

## Related

- `documentation/docs/policies/lessons/kv-cache-stampede-lessons.md`
- `documentation/docs/policies/architecture/worker-bundle-optimisation.md`
- Cloudflare Workers — CPU time limits

---

## Sources

- Cloudflare Workers documentation — Runtime APIs, Limits
- Internal performance review: `perf/2025-Q3-cold-start-investigation.md`
- esbuild documentation — Bundle analysis
- "The Cost of JavaScript" — Addy Osmani (adapted for Workers context)
