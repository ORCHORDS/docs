# Lazy Initialization and Module-Level Caching in Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
CPU time per request spikes because expensive one-time work (key import, schema compilation, regex construction, Wasm module parsing) runs on every invocation. You need a way to pay the cost once per isolate lifetime and share the result across all requests handled by that isolate.

## Context
Cloudflare Workers run in V8 isolates that are reused across many requests within the same data-center instance. Module-level variables survive across requests within one isolate lifetime, making them ideal for caching parsed or compiled artifacts. However, isolates are ephemeral and each cold-start re-executes module-level code, so initialization must be fast on first access and idempotent on subsequent ones.

## Module-Level Singleton Pattern
Wrap expensive construction in a `Promise` stored at module scope. Concurrent requests that arrive before the first promise resolves share the same initialization future rather than racing to re-initialize.

```typescript
// singleton.ts
let _initPromise: Promise<{ key: CryptoKey; schema: CompiledSchema }> | null = null;

async function init(env: Env): Promise<{ key: CryptoKey; schema: CompiledSchema }> {
  if (!_initPromise) {
    _initPromise = (async () => {
      const rawKey = JSON.parse(env.SIGNING_KEY_JSON);
      const key = await crypto.subtle.importKey(
        'jwk', rawKey, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign', 'verify'],
      );
      const schema = compileSchema(JSON.parse(env.REQUEST_SCHEMA));
      return { key, schema };
    })();
  }
  return _initPromise;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const { key, schema } = await init(env);
    // key and schema are reused on all subsequent requests in this isolate
    return handleRequest(request, key, schema);
  },
};
```

## Lazy CryptoKey Import
`crypto.subtle.importKey` is synchronous in terms of scheduling but wraps native crypto; calling it once and caching the `CryptoKey` object saves ~0.2–1 ms per request on typical HMAC keys.

```typescript
const keyCache = new Map<string, CryptoKey>();

async function getSigningKey(env: Env): Promise<CryptoKey> {
  const cacheKey = 'signing-v1';
  if (keyCache.has(cacheKey)) return keyCache.get(cacheKey)!;

  const jwk = JSON.parse(env.HMAC_KEY_JWK) as JsonWebKey;
  const key = await crypto.subtle.importKey(
    'jwk', jwk,
    { name: 'HMAC', hash: { name: 'SHA-256' } },
    false,
    ['sign', 'verify'],
  );
  keyCache.set(cacheKey, key);
  return key;
}

async function verifyHmac(env: Env, signature: string, body: string): Promise<boolean> {
  const key = await getSigningKey(env);
  const enc = new TextEncoder();
  const sig = Uint8Array.from(atob(signature), c => c.charCodeAt(0));
  return crypto.subtle.verify({ name: 'HMAC', hash: 'SHA-256' }, key, sig, enc.encode(body));
}
```

## Compiled Regex and Schema Caching
Regex compilation and JSON-schema compilation are CPU-bound. Run them once at module scope or inside the lazy-init promise so they do not re-run per request.

```typescript
// Regex built once at module evaluation time — this runs on every cold start
// but cold starts are rare compared to warm requests.
const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const VERSION_RE = /^v(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.]+))?$/;

// Heavier schema compiler: lazy inside init promise
type CompiledSchema = (data: unknown) => boolean;

function compileSchema(raw: Record<string, unknown>): CompiledSchema {
  // Replace with your preferred JSON-schema library (e.g. ajv compiled to WASM)
  const required = new Set(raw['required'] as string[] ?? []);
  return (data: unknown): boolean => {
    if (typeof data !== 'object' || data === null) return false;
    return [...required].every(k => k in (data as Record<string, unknown>));
  };
}

let _schema: CompiledSchema | null = null;

function getSchema(rawSchemaJson: string): CompiledSchema {
  if (!_schema) {
    _schema = compileSchema(JSON.parse(rawSchemaJson));
  }
  return _schema;
}
```

## Wasm Module Caching
`WebAssembly.compile()` is expensive. Compile the module once and store the `WebAssembly.Module` at module scope; instantiation per-request is then cheap.

```typescript
// wasm-cache.ts
// Wrangler supports top-level `await` in module workers
// Import the raw bytes via the `=` syntax in wrangler.toml or inline fetch:
let _wasmModule: WebAssembly.Module | null = null;

async function getWasmModule(env: Env): Promise<WebAssembly.Module> {
  if (_wasmModule) return _wasmModule;

  // Fetch from R2 or inline the binary via wrangler.toml WASM binding
  const bytes = await env.ASSETS.fetch('wasm/compute.wasm').then(r => r.arrayBuffer());
  _wasmModule = await WebAssembly.compile(bytes);
  return _wasmModule;
}

async function runWasm(env: Env, input: Uint8Array): Promise<Uint8Array> {
  const module = await getWasmModule(env);
  const instance = await WebAssembly.instantiate(module, {
    env: { memory: new WebAssembly.Memory({ initial: 4 }) },
  });
  const exports = instance.exports as { process: (ptr: number, len: number) => number };
  // ... write input into memory, call exports.process, read output
  return new Uint8Array(0); // placeholder
}
```

## Anti-patterns
- Storing mutable per-request state at module scope — isolates are shared; cross-request state leaks user data.
- Relying on module-scope variables for data that must be fresh on every request (feature flags, secrets rotated live) — use KV or a secrets binding instead.
- Catching errors in the init promise and silently swallowing them — a failed `_initPromise` stays cached, making every subsequent request fail silently.
- Storing large buffers (multi-MB Wasm binaries) at module scope on resource-constrained plans — monitor isolate memory use via `wrangler tail`.
- Initializing with `env` values inside top-level `await` in non-ESM workers — only ESM module workers support `export default { fetch }` with `env`.

## Gotchas
- A rejected `Promise` stored at module scope will be returned on all subsequent calls; reset it to `null` in the `catch` branch so retries work.
- Isolates are scoped per data-center PoP; you may have hundreds of isolates globally, each running their own cold-start initialization — your origin must handle the burst.
- `wrangler dev` creates a new isolate per hot-reload, so module-scope caches are invalidated on every file save during development.
- Workers on the Free plan have a 5 ms CPU time limit; lazy-init cost must fit within that budget on the cold-start request.
- `crypto.subtle.importKey` with `extractable: false` is the correct security posture; do not store raw key material at module scope.

## Verification
1. Add timing logs: `const t0 = Date.now(); const { key } = await init(env); console.log('init ms', Date.now() - t0)` — on a warm request this should be ~0 ms.
2. `wrangler tail` with `--format pretty` shows CPU time per invocation; confirm it drops after the first request to an isolate.
3. Unit-test the singleton: call `init()` twice concurrently in a Vitest worker environment and assert `_initPromise` is the same reference.
4. Chaos-test: cause the init promise to reject on the first call and verify the second call re-initializes rather than returning the rejected promise.

## Related
- `/documentation/docs/policies/patterns/circuit-breaker-workers-d1-fetch.md`
- `/documentation/docs/policies/patterns/exponential-backoff-jitter-workers.md`
- `/documentation/docs/policies/patterns/scaling-cf-workers.md`

## Sources
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/workers/platform/limits/#worker-limits
- https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- https://v8.dev/blog/cost-of-javascript-2019 (regex compilation cost)
