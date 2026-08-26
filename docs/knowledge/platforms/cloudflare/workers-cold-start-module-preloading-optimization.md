# Workers Cold Start Optimization with Module-Scope Preloading

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Your Worker's first request after a cold start takes 300–800 ms longer than warm requests because expensive initialisation — JSON schema parsing, Wasm module compilation, regex pre-compilation, or crypto key import — happens inside the request handler instead of at module load time.

## Context
Workers run in V8 isolates. When a new isolate is spun up (cold start), the JavaScript module is evaluated top-to-bottom synchronously before the first request arrives. Any `await`-able work done at **module scope** via `async` top-level expressions is NOT supported in Workers; however, synchronous initialisation and lazy singleton patterns with `Promise` caching move heavy work out of the hot path. Cloudflare Smart Placement and the `nodejs_compat` flag also affect cold-start characteristics. This article covers practical patterns to minimise p99 cold-start latency.

## Baseline: What Triggers a Cold Start
- New deployment — all existing isolates are replaced.
- Traffic spike exceeding current isolate pool capacity.
- Low-traffic Workers: idle isolates are evicted after ~30 s; requests to a quiet Worker nearly always hit a cold start.
- Wrangler `dev` mode: every file-save triggers a reload.

A cold start is measurable via `server-timing` headers when using `ctx.passThroughOnException()` or via Tail Workers.

## Pattern 1 — Module-Scope Synchronous Pre-computation

```typescript
// src/index.ts
// These run ONCE at module evaluation time, not per-request
import { compile } from "path-to-regexp";

// Pre-compile route patterns (synchronous)
const ROUTE_PATTERNS = [
  { pattern: compile("/api/users/:id"), name: "user-detail" },
  { pattern: compile("/api/posts/:slug"), name: "post-detail" },
  { pattern: compile("/api/search"), name: "search" },
];

// Pre-parse static JSON config (avoids per-request JSON.parse)
// In module Workers, import JSON directly for bundler inlining
import CONFIG from "./config.json";
const ALLOWED_ORIGINS = new Set<string>(CONFIG.allowedOrigins);
const FEATURE_FLAGS = new Map<string, boolean>(Object.entries(CONFIG.features));

export interface Env {
  KV: KVNamespace;
  DB: D1Database;
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const origin = req.headers.get("Origin") ?? "";
    if (!ALLOWED_ORIGINS.has(origin)) {
      return new Response("Forbidden", { status: 403 });
    }
    // ROUTE_PATTERNS, FEATURE_FLAGS are already initialised — zero cost here
    return new Response("OK");
  },
} satisfies ExportedHandler<Env>;
```

## Pattern 2 — Lazy Singleton with Promise Caching

For work that cannot be synchronous (crypto key import, Wasm instantiation), use a module-level `Promise` variable that is initialised on first request and reused across all subsequent requests in the same isolate.

```typescript
// src/crypto-key.ts
let cachedKeyPromise: Promise<CryptoKey> | null = null;

// Raw HMAC key bytes — embed at build time via environment or import
const RAW_KEY_B64 = "YOUR_BASE64_KEY_HERE";

export function getSigningKey(): Promise<CryptoKey> {
  if (cachedKeyPromise !== null) return cachedKeyPromise;

  cachedKeyPromise = crypto.subtle.importKey(
    "raw",
    Uint8Array.from(atob(RAW_KEY_B64), (c) => c.charCodeAt(0)),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"]
  );

  return cachedKeyPromise;
}
```

```typescript
// src/wasm-module.ts
// Wasm compilation is the most expensive cold-start cost (~100–400 ms for large modules)
// Workers runtime compiles Wasm synchronously when you call `new WebAssembly.Instance`
// Use the module cache pattern to compile once per isolate

// Import Wasm as a module (wrangler bundles it automatically)
import wasmModule from "./my_module_bg.wasm";

let cachedInstance: WebAssembly.Instance | null = null;
let cachedImports: ReturnType<typeof createImports> | null = null;

function createImports(memory: WebAssembly.Memory) {
  return { env: { memory } };
}

export function getWasmInstance(): WebAssembly.Instance {
  if (cachedInstance !== null) return cachedInstance;

  const memory = new WebAssembly.Memory({ initial: 16, maximum: 256 });
  const imports = createImports(memory);
  // Synchronous instantiation — runs once per isolate
  cachedInstance = new WebAssembly.Instance(wasmModule, imports);
  cachedImports = imports;
  return cachedInstance;
}
```

## Pattern 3 — Warm-Up via `waitUntil` on First Request

```typescript
// src/index.ts
import { getSigningKey } from "./crypto-key";
import { getWasmInstance } from "./wasm-module";

let warmed = false;

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Trigger pre-warming in background on the very first request
    // so the SECOND request pays no initialisation cost
    if (!warmed) {
      warmed = true;
      ctx.waitUntil(
        Promise.all([
          getSigningKey(),
          // Wasm instance is sync so just calling it here suffices
          Promise.resolve(getWasmInstance()),
        ])
      );
    }

    const key = await getSigningKey();
    // ... use key
    return new Response("OK");
  },
} satisfies ExportedHandler<Env>;
```

## Pattern 4 — Bundle Size Reduction (Fewer Modules = Faster Parse)

```typescript
// wrangler.toml
// Minify removes whitespace and mangles names; tree-shaking (automatic with esbuild)
// eliminates unused exports from large packages like lodash or date-fns
[build]
minify = true

// Avoid importing entire libraries; prefer named deep-imports
// ❌ import _ from "lodash"              // pulls in ~75 KB
// ✓  import { debounce } from "lodash"   // still pulls in the whole package via esbuild
// ✓✓ import debounce from "lodash/debounce"  // tree-shakes cleanly
```

Measure bundle size:
```bash
npx wrangler deploy --dry-run --outdir dist
ls -lh dist/*.js   # target < 1 MB for p99 cold-start < 50 ms
```

## Pattern 5 — Smart Placement for Low-Latency Warm Requests

```toml
# wrangler.toml
[placement]
mode = "smart"
```

Smart Placement routes requests to the PoP closest to your D1/Hyperdrive backends, which keeps isolates warm because a smaller number of PoPs receives traffic — reducing the total cold-start surface area.

## Measuring Cold-Start Latency

Via Tail Worker:
```typescript
// tail.ts
export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      if (event.scriptName !== "my-worker") continue;
      for (const log of event.logs) {
        if (log.message[0] === "COLD_START") {
          // Ship to Analytics Engine
          console.log("cold_start_ms", log.message[1]);
        }
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

Instrument your Worker:
```typescript
let isFirstRequest = true;
const moduleLoadedAt = Date.now();

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (isFirstRequest) {
      isFirstRequest = false;
      console.log("COLD_START", Date.now() - moduleLoadedAt);
    }
    // ...
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns
- **Awaiting top-level `await` for heavy async work** — Workers do not support top-level `await` in the main module; it throws a syntax or runtime error.
- **Re-importing or re-parsing the same JSON on every request** — move `JSON.parse` to module scope or use static `import` (bundler inlines and tree-shakes).
- **`new WebAssembly.Instance(module, imports)` inside the fetch handler** — Wasm instantiation is synchronous and CPU-heavy; it blocks the event loop for every cold start on every request.
- **Large unminified bundles** — every extra KB of JS adds ~0.5–2 ms of parse time per cold start; minify and tree-shake aggressively.
- **Using `setTimeout` for warm-up hacks** — Workers do not have a persistent event loop between requests; `setTimeout` callbacks do not fire until the next request is handled.

## Gotchas
- Module-scope `Promise` caching survives across requests within **the same isolate** but is reset on each cold start — it only amortises the cost for the second and later requests in that isolate's lifetime.
- `cachedKeyPromise` will be the rejected promise if `importKey` throws; add a `.catch(() => { cachedKeyPromise = null; })` reset so the next request can retry.
- Wasm modules imported via `import foo from "./foo.wasm"` are compiled by the runtime before the module script runs; the `.wasm` file size directly affects deployment upload time, not cold-start time (compilation is pre-done by Cloudflare on upload).
- `warmed = true` is set on the first cold-start request, not on every isolate; because isolates are single-threaded there is no data race.
- `nodejs_compat` flag enables Node.js polyfills but adds ~50–100 KB to the bundle; only enable it if you genuinely need Node APIs.

## Verification
1. Deploy and send 10 rapid requests; inspect Tail Worker logs — only the first should emit `COLD_START`.
2. Wait 60 seconds (isolate eviction window), send another request — `COLD_START` fires again confirming the warm-up path.
3. Compare p99 latency before/after moving crypto key import to module scope using the Workers metrics dashboard.
4. `npx wrangler deploy --dry-run --outdir dist && du -sh dist/` — confirm bundle is under target size.

## Related
- `workers-resource-limits.md`
- `workers-mutable-globals-module-scope.md`
- `workers-tail-workers.md`
- `smart-placement-best-practices.md`
- `workers-nodejs-compatibility.md`

## Sources
- https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- https://developers.cloudflare.com/workers/observability/metrics-and-analytics/
- https://developers.cloudflare.com/workers/configuration/smart-placement/
