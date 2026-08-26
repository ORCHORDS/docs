# Cloudflare Workers Cold Start Optimization via Bundle Size Reduction

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A newly deployed Cloudflare Worker exhibits p99 latency spikes of 200–600 ms on the first request after a code update or after a long idle period. Profiling confirms the overhead is in script parse/evaluation, not in application logic. Reducing the compressed bundle size below 1 MB consistently eliminates the cold start penalty on Cloudflare's V8 isolate recycling boundary.

## Context

Cloudflare Workers run inside V8 isolates that are lazily recycled across PoPs. When an isolate for a given Worker script version is not warm, the runtime must parse and evaluate the entire script before the first request can be handled. Unlike Node.js, there is no persistent JIT cache across cold starts. Every byte in the bundle contributes directly to parse time. The Workers platform imposes a 10 MB compressed script limit, but best practice is to stay under 1 MB compressed and under 3 MB uncompressed to maintain sub-5 ms cold starts globally. Wrangler's build pipeline (esbuild) bundles all imports into a single file by default; without deliberate tree-shaking and code splitting, SDKs like `aws-sdk-v3`, `zod`, or `opentelemetry` can bloat the bundle to 4–8 MB.

## Measuring Baseline Bundle Size and Parse Time

Before optimizing, establish a baseline using Wrangler's built-in analysis and the Workers Tail API.

```typescript
// tail-cold-start.ts — deploy as a Tail Worker to capture cold start events
export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      if (event.scriptName !== "my-api-worker") continue;

      const coldStartMs = event.cpuTime - event.wallTime;
      // cpuTime > wallTime gap signals parse overhead on first isolate use
      if (coldStartMs > 10) {
        await env.METRICS_QUEUE.send({
          type: "cold_start",
          scriptName: event.scriptName,
          cpuMs: event.cpuTime,
          wallMs: event.wallTime,
          parsePenaltyMs: coldStartMs,
          timestamp: Date.now(),
        });
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

```bash
# Analyse bundle composition before optimising
npx wrangler deploy --dry-run --outdir dist/
ls -lh dist/
# Check gzip size — this is what Cloudflare uploads and cold-starts parse
gzip -k dist/index.js && ls -lh dist/index.js.gz

# Detailed module-level breakdown via esbuild metafile
npx esbuild src/index.ts \
  --bundle \
  --platform=browser \
  --target=es2022 \
  --metafile=dist/meta.json \
  --outfile=dist/index.js
npx esbuild-visualizer --metadata dist/meta.json --open
```

## Tree-Shaking and Import Optimisation

Most bundle bloat originates from barrel imports and side-effectful modules. Use named imports and configure esbuild to mark packages as side-effect-free.

```typescript
// BAD — pulls in the entire zod library including error formatters
import zod from "zod";

// GOOD — named import; esbuild can tree-shake unused validators
import { z, ZodError } from "zod";

// wrangler.toml — custom esbuild options via a build config file
// wrangler.toml
// [build]
// command = "node esbuild.config.mjs"
```

```javascript
// esbuild.config.mjs
import { build } from "esbuild";
import { readFileSync } from "fs";

const pkg = JSON.parse(readFileSync("./package.json", "utf8"));

await build({
  entryPoints: ["src/index.ts"],
  bundle: true,
  platform: "browser",
  target: "es2022",
  format: "esm",
  outfile: "dist/index.js",
  minify: true,
  treeShaking: true,
  // Mark packages that declare sideEffects: false explicitly
  // so esbuild can drop unused re-exports from barrels
  mainFields: ["module", "browser", "main"],
  conditions: ["worker", "browser", "module", "import", "default"],
  external: [
    // Cloudflare built-ins — never bundle these
    "cloudflare:sockets",
    "cloudflare:workers",
    "node:buffer",
    "node:crypto",
    "node:stream",
    "node:util",
  ],
  define: {
    "process.env.NODE_ENV": '"production"',
  },
  metafile: true,
});
```

## Lazy Initialisation and Dynamic Import Patterns

V8 parses every function body at script evaluation time, but defers compilation of functions not called during startup. Move heavy SDK initialisation behind a lazy singleton to shift work to first request rather than cold start.

```typescript
// utils/lazy-db.ts
let _db: D1Database | null = null;

export function getDb(env: Env): D1Database {
  // Avoids running SDK setup during script evaluation
  if (!_db) {
    _db = env.DB;
  }
  return _db;
}

// Heavy OpenTelemetry SDK — only initialise on first real request
let _tracer: ReturnType<typeof initTracer> | null = null;

function initTracer(env: Env) {
  // Import happens at module evaluation time anyway in Workers,
  // so use conditional logic to skip expensive setup when not needed
  if (env.ENVIRONMENT !== "production") {
    return { startSpan: () => ({ end: () => {} }) };
  }
  const { trace } = require("@opentelemetry/api"); // dynamic require avoids top-level side effects
  return trace.getTracer("my-worker", "1.0.0");
}

export function getTracer(env: Env) {
  if (!_tracer) _tracer = initTracer(env);
  return _tracer;
}
```

## Anti-patterns

- Importing `lodash` or `ramda` via barrel (`import _ from 'lodash'`) — adds 70–500 KB uncompressed; use `lodash-es` with named imports or replace with native equivalents.
- Bundling `@aws-sdk/client-s3` to call Cloudflare R2 — the AWS SDK adds 2+ MB; use the `aws4fetch` micro-library (< 5 KB) instead.
- Using `require()` at the top level inside Workers — esbuild cannot tree-shake CommonJS barrels, preventing dead-code elimination.
- Skipping `minify: true` in production builds — minification alone reduces bundle size by 30–50 %.
- Running `wrangler deploy` without reviewing bundle size in CI — bundle bloat goes undetected until p99 regressions appear in production.

## Gotchas

- Cloudflare's isolate recycling is PoP-local; a Worker may be warm in FRA but cold in SYD simultaneously, making cold start regressions appear intermittent in global latency dashboards.
- The `--minify` flag in Wrangler uses esbuild's minifier, which does not perform advanced dead-code elimination across module boundaries without `treeShaking: true` explicitly set in a custom build script.
- `node:crypto` and `node:stream` are re-exported as Worker built-ins; bundling polyfills for them doubles the parse cost for those modules.

## Verification

```bash
# Assert compressed bundle stays under 900 KB in CI
BUNDLE_GZ_BYTES=$(gzip -c dist/index.js | wc -c)
LIMIT=921600  # 900 KB
if [ "$BUNDLE_GZ_BYTES" -gt "$LIMIT" ]; then
  echo "FAIL: bundle ${BUNDLE_GZ_BYTES} bytes exceeds ${LIMIT} byte limit"
  exit 1
fi
echo "OK: bundle is ${BUNDLE_GZ_BYTES} bytes compressed"

# Tail cold-start metric from Cloudflare Logpush (after deployment)
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/my-api-worker/tail" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result.cpu_time_p99'
```

## Related

- `infra/wrangler-deploys.md`
- `infra/workerd-local-dev-setup.md`
- `infra/workers-opentelemetry-tail-workers.md`
- `infra/cloudflare-workers-limits-resource-planning.md`

## Sources

- https://developers.cloudflare.com/workers/platform/limits/#worker-size
- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://esbuild.github.io/api/#tree-shaking
