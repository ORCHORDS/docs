# Lazy Module Initialization in Cloudflare Workers for Cold Start Performance

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker experiences cold start latency spikes of 50–300 ms on the first request after a new isolate is created. CPU time is consumed before the `fetch` handler even begins executing. Subsequent requests in the same isolate are fast, but traffic patterns that cause frequent isolate recycling make the problem recur unpredictably.

## Context

Cloudflare Workers execute module-level code synchronously during isolate startup, before any request is handled. Expensive operations placed at module scope — JSON schema compilation, regex pre-compilation, WASM module instantiation, large lookup-table construction — are paid on every cold start. Workers isolates are not long-lived: Cloudflare recycles them under memory pressure, after idle periods, or during deployments. Deferring these initializations to the first actual request call reduces the p99 cold-start cost to near zero, shifting the one-time cost onto a single warm request instead.

## Lazy Initialization Pattern

```typescript
// src/lazy.ts  — generic lazy singleton helper
export function lazyInit<T>(factory: () => T): () => T {
  let instance: T | null = null;
  return (): T => {
    if (instance === null) {
      instance = factory();
    }
    return instance;
  };
}

// src/schema.ts — compiled JSON schema, deferred
import Ajv from 'ajv';
import { lazyInit } from './lazy';

const getValidator = lazyInit(() => {
  const ajv = new Ajv({ allErrors: true, coerceTypes: false });
  return ajv.compile({
    type: 'object',
    required: ['id', 'name'],
    properties: {
      id:   { type: 'string', minLength: 1 },
      name: { type: 'string', maxLength: 256 },
    },
    additionalProperties: false,
  });
});

// src/regex.ts — expensive pre-compiled regex, deferred
const getSlugPattern = lazyInit(
  () => /^[a-z0-9]+(?:-[a-z0-9]+)*$/i
);

// src/wasm.ts — WASM instantiation, deferred
let _wasmInstance: WebAssembly.Instance | null = null;
async function getWasmInstance(env: Env): Promise<WebAssembly.Instance> {
  if (_wasmInstance) return _wasmInstance;
  // Fetch the WASM binary from an R2 binding or inline base64
  const wasmBytes = await env.WASM_BUCKET.get('processor.wasm');
  if (!wasmBytes) throw new Error('WASM binary not found');
  const { instance } = await WebAssembly.instantiate(
    await wasmBytes.arrayBuffer()
  );
  _wasmInstance = instance;
  return instance;
}

// src/index.ts — handler uses lazy getters
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const validate = getValidator();
    const slugRe  = getSlugPattern();
    const wasm    = await getWasmInstance(env);

    const body = await request.json();
    if (!validate(body)) {
      return Response.json({ errors: validate.errors }, { status: 400 });
    }

    const slug = (body as any).name.toLowerCase().replace(/\s+/g, '-');
    if (!slugRe.test(slug)) {
      return Response.json({ error: 'invalid slug' }, { status: 422 });
    }

    // use wasm instance ...
    return Response.json({ ok: true });
  },
} satisfies ExportedHandler<Env>;
```

## Measuring Cold Start with Wrangler Tail

```bash
# Stream live logs including CPU time
npx wrangler tail --format=json | \
  jq '{event: .event.request.url, cpu_ms: .event.cpuTime, wall_ms: .event.wallTime}'

# Filter only cold-start events (cpuTime spikes > 20 ms indicate schema/WASM init)
npx wrangler tail --format=json | \
  jq 'select(.event.cpuTime > 20) | {url: .event.request.url, cpu: .event.cpuTime}'
```

## Eager vs Lazy CPU Time Comparison

| Initialization strategy | Isolate cold-start CPU | First-request overhead | Steady-state |
|-------------------------|------------------------|------------------------|--------------|
| Eager (module scope)    | 45–180 ms              | ~0 ms                  | ~0 ms        |
| Lazy (`getOrInit`)      | <2 ms                  | 45–180 ms (once)       | ~0 ms        |

For APIs with uneven traffic (burst, then idle), lazy initialization wins because isolates are frequently recycled during idle gaps, meaning many cold starts would bear the full eager cost. Lazy init shifts the cost to the first warmed request per isolate lifecycle, which is a better trade-off.

## Module-Scope Side-Effects to Avoid

The following patterns executed at module scope cause measurable cold-start CPU overhead:

- Calling `JSON.parse` on large embedded JSON blobs (use `import` with `with { type: 'json' }` to let the engine cache)
- Constructing `RegExp` objects from complex patterns with many capture groups
- `new Intl.Collator()` / `new Intl.DateTimeFormat()` — locale data loading is expensive
- `crypto.subtle.generateKey()` — defer key derivation or use pre-generated keys from secrets
- Dynamic `import()` chains that trigger additional module evaluation

## Anti-patterns

- **Global `const validator = new Ajv().compile(schema)`** — runs on every cold start; wrap in `lazyInit` instead.
- **WASM `instantiate` at top level** — async at module scope is not supported; always gate behind a request-triggered async getter.
- **Caching lazily initialized state in a KV binding at module scope** — KV bindings are only available inside request handlers, not during module initialization.

## Gotchas

- The `lazyInit` closure captures a `null` reference per isolate, not globally; you get one initialization per isolate, which is the intended behavior.
- If your lazy factory throws, the `null` guard means the next request will retry the factory. Add a separate `_initError` flag if you want fail-fast behavior after a permanent error.
- Durable Object class constructors run once per DO instance, not per isolate cold start — lazy init is less critical there but still valid.
- `wrangler dev` keeps a single long-lived isolate; you will not observe cold starts locally. Use `wrangler tail` against the deployed environment.

## Verification

```bash
# Deploy and observe CPU time on first request after a forced isolate recycle
npx wrangler deploy

# Wait 30 s for idle recycle, then hit the endpoint and capture CPU time
curl -s https://your-worker.workers.dev/api/validate -d '{"id":"1","name":"test"}' \
  -H 'Content-Type: application/json'

# Tail logs and look for cpuTime difference between isolate-first and subsequent calls
npx wrangler tail --format=json | jq '{cpuTime: .event.cpuTime}'
```

## Related

- `d1-prepared-statement-cache-performance.md`
- `cloudflare-snippets-vs-workers-latency.md`

## Sources

- Cloudflare Workers Runtime APIs — https://developers.cloudflare.com/workers/runtime-apis/
- Cloudflare Workers Cold Start Optimization — https://developers.cloudflare.com/workers/platform/cold-starts/
- Wrangler Tail — https://developers.cloudflare.com/workers/wrangler/commands/#tail
