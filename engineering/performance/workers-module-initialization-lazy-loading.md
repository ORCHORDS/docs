# Workers Module Initialization and Lazy Loading

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Cloudflare Worker that loads a database ORM, validates a JSON schema, or decrypts a
configuration secret at module scope shows elevated latency on its first request after
isolate creation. Wrangler logs show `Script startup exceeded limit` warnings, or P99
latency spikes during rolling deployments when new isolates are provisioned across PoPs.
The Worker feels fast for warm requests but unpredictably slow for the first hit per
isolate lifetime.

## Context

Cloudflare Workers use V8 isolates. Each isolate executes module-scope code exactly once
at creation time, then reuses the resulting JavaScript heap across all requests served by
that isolate. Isolates are created on demand (cold start) and can be evicted after idle
periods. Module-scope code therefore runs on isolate creation — not on every request —
but that cost is paid on the first request after a cold start or deployment.

The Workers runtime snapshots V8 heap state after module evaluation and can restore isolates
from that snapshot, which reduces the per-isolate startup cost for most Workers. However,
any code that cannot be snapshotted (I/O, crypto operations requiring OS entropy, dynamic
imports that resolve at runtime) must run on each isolate creation and cannot benefit from
the snapshot optimisation.

Lazy initialization defers expensive work to the first request that needs it, and caches
the result in module scope so that subsequent requests in the same isolate pay nothing.

## Lazy Singleton Pattern

The simplest pattern: a module-scope variable initialized to `undefined` and populated on
first use. The initialization function is called once per isolate, not once globally.

```typescript
// Bad: expensive work runs at module load time (blocks isolate startup)
import { createPool } from './db';
const pool = createPool(process.env.DB_URL); // runs before first request

// Good: deferred initialization
import { createPool, Pool } from './db';

let _pool: Pool | undefined;

function getPool(env: Env): Pool {
  if (!_pool) {
    _pool = createPool(env.DB_URL);
  }
  return _pool;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const pool = getPool(env); // initialized only on first request
    const result = await pool.query('SELECT 1');
    return Response.json(result);
  },
};
```

## Async Lazy Initialization with Promise Caching

When initialization is asynchronous (fetching a secret, connecting to a service), cache
the Promise itself so concurrent first-requests do not race to initialize in parallel.

```typescript
interface Env {
  SECRET_KV: KVNamespace;
}

let _configPromise: Promise<AppConfig> | undefined;

async function getConfig(env: Env): Promise<AppConfig> {
  if (!_configPromise) {
    // Store the Promise, not the resolved value.
    // Concurrent callers await the same Promise — only one fetch runs.
    _configPromise = env.SECRET_KV.get('app-config', 'json') as Promise<AppConfig>;
  }
  return _configPromise;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const config = await getConfig(env);
    return new Response(`Region: ${config.region}`);
  },
};
```

## Time-Bounded Cache for Refresh Without Cold Start

Module-scope caches persist for the isolate's lifetime (minutes to hours). For secrets
that rotate, add a TTL so the cache refreshes without requiring a new isolate.

```typescript
interface CacheEntry<T> {
  value: T;
  expiresAt: number;
}

function makeTTLCache<T>(ttlMs: number) {
  let entry: CacheEntry<T> | undefined;

  return {
    async get(fetcher: () => Promise<T>): Promise<T> {
      const now = Date.now();
      if (!entry || entry.expiresAt < now) {
        entry = { value: await fetcher(), expiresAt: now + ttlMs };
      }
      return entry.value;
    },
    invalidate() { entry = undefined; },
  };
}

const signingKeyCache = makeTTLCache<CryptoKey>(5 * 60 * 1000); // 5 min TTL

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const signingKey = await signingKeyCache.get(async () => {
      const raw = await env.SECRETS.get('signing-key', 'arrayBuffer');
      return crypto.subtle.importKey('raw', raw!, { name: 'HMAC', hash: 'SHA-256' },
        false, ['sign']);
    });
    const sig = await crypto.subtle.sign('HMAC', signingKey,
      new TextEncoder().encode(request.url));
    return new Response(btoa(String.fromCharCode(...new Uint8Array(sig))));
  },
};
```

## Dynamic Import for Rarely-Used Code Paths

Heavy modules (PDF renderers, Wasm parsers, image codecs) can be loaded with `import()`
inside the handler so they only contribute to bundle parse time when actually needed.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname.startsWith('/export/pdf')) {
      // Loaded only for this path; parsed once per isolate that serves a PDF request.
      const { renderPDF } = await import('./pdf-renderer');
      const data = await fetchReportData(env, url.searchParams);
      const pdf = await renderPDF(data);
      return new Response(pdf, { headers: { 'Content-Type': 'application/pdf' } });
    }

    return new Response('OK');
  },
};
```

Note: Dynamic imports contribute to the Worker bundle's total size limit. They do not
reduce the compressed bundle size, only the parse time per isolate that does not execute
that code path.

## Wasm Module Pre-Instantiation

For Workers that use WebAssembly, compile the module at module scope (fast, snapshotted)
and instantiate it lazily per-isolate to avoid re-compilation cost.

```typescript
// wasm module loaded at module scope — compilation is cached in the snapshot
import wasmBytes from './parser.wasm';
const wasmModule = new WebAssembly.Module(wasmBytes);

let _wasmInstance: WebAssembly.Instance | undefined;

function getWasmInstance(): WebAssembly.Instance {
  if (!_wasmInstance) {
    _wasmInstance = new WebAssembly.Instance(wasmModule, {});
  }
  return _wasmInstance;
}

export default {
  async fetch(request: Request): Promise<Response> {
    const instance = getWasmInstance();
    const exports = instance.exports as { parse: (ptr: number, len: number) => number };
    // ... use wasm exports
    return new Response('parsed');
  },
};
```

## Anti-patterns

- **Top-level await for I/O**: `const config = await fetchConfig()` at module scope
  blocks isolate startup for every cold start and cannot be snapshotted.
- **Importing entire libraries when only one function is needed**: `import _ from 'lodash'`
  adds 72 KB of parse work. Import only `{ debounce }` from lodash-es or use a native
  alternative.
- **Re-initializing on every request**: placing `const pool = createPool(...)` inside the
  `fetch` handler recreates the pool on every request, defeating connection reuse.
- **Relying on module-scope cache as durable storage**: isolates are evicted; module-scope
  state is not shared between isolates or across restarts. Use KV or D1 for durable state.

## Gotchas

- The V8 snapshot only persists pure JavaScript state. Objects holding OS handles (file
  descriptors, sockets) cannot survive a snapshot restore.
- `globalThis` is shared across all requests in the same isolate but not across isolates.
  Two isolates serving the same Worker do not share module-scope state.
- Workers AI and some built-in bindings must be accessed inside a handler, not at module
  scope, because they require a request context.
- Dynamic `import()` inside a Worker resolves at bundle time, not truly at runtime. The
  bundler inlines the module into the bundle; `import()` only affects when the V8 parser
  evaluates that module chunk within the isolate.

## Verification

1. Check startup cost with `wrangler dev --log-level debug` — look for `Script startup`
   timing in the console.
2. Use Cloudflare Workers Analytics to plot P99 latency against invocation count. High P99
   with lower P50 often indicates initialization cost on cold isolates.
3. Add a `Date.now()` timestamp at module scope and inside the handler; the delta is the
   module initialization time visible on the first request:
   ```typescript
   const MODULE_INIT_AT = Date.now();
   export default {
     async fetch(req: Request): Promise<Response> {
       const initMs = Date.now() - MODULE_INIT_AT;
       return new Response(`Module initialized ${initMs}ms ago`);
     },
   };
   ```
4. Profile bundle parse cost: `wrangler build && ls -lh dist/` — bundles over 300 KB
   (uncompressed) will show measurable parse time per isolate creation.

## Related

- `workers-cold-start-optimization.md`
- `workers-wasm-module-caching.md`
- `workers-memory-allocation-optimization.md`
- `dead-code-elimination.md`
- `javascript-bundle-size.md`

## Sources

- Cloudflare Workers V8 Isolates Architecture — https://developers.cloudflare.com/workers/reference/how-workers-works/
- Workers Bundle Size Limits — https://developers.cloudflare.com/workers/platform/limits/#worker-size
- WebAssembly in Workers — https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- V8 Snapshots and Startup Performance — https://v8.dev/blog/custom-startup-snapshots
