# Workers Mutable Globals — Module-Scope Initialization and Per-Isolate Caching

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Workers handler re-initialises an SDK client, compiles a regex, or fetches a config value on every request. CPU time and external call counts are higher than expected. Alternatively, a previous request's data appears to "leak" into subsequent requests served by the same isolate — a sign that mutable request-scoped state was mistakenly placed at module scope.

## Context

Cloudflare Workers use V8 isolates that are created once and reused across many sequential requests on the same instance. Module-scope (global) variables persist for the lifetime of the isolate, making them ideal for expensive one-time work (client construction, compiled patterns, static config) but dangerous for request-scoped state. Isolates are evicted under memory pressure and rotated on redeployment; code must tolerate cold starts and re-initialisation.

## 1 — Safe Module-Scope Singletons (Lazy Init)

```typescript
// Initialise once per isolate, not once per request
let _redisClient: RedisClient | null = null;

function getRedisClient(url: string): RedisClient {
  if (!_redisClient) {
    _redisClient = new RedisClient({ url });
  }
  return _redisClient;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const redis = getRedisClient(env.REDIS_URL);
    const value = await redis.get('some-key');
    return new Response(value);
  },
};
```

## 2 — Async Lazy Init with Promise Caching

Avoid running async initialisation on every request by caching the Promise itself, so concurrent cold-start requests share the same in-flight init.

```typescript
let initPromise: Promise<AppConfig> | null = null;

async function getConfig(env: Env): Promise<AppConfig> {
  if (!initPromise) {
    initPromise = (async () => {
      const raw = await env.CONFIG_KV.get('app-config', 'json');
      return raw as AppConfig;
    })();
  }
  return initPromise;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const config = await getConfig(env);
    return new Response(JSON.stringify(config));
  },
};
```

## 3 — Compiled Regex and Static Lookup Tables

```typescript
// Compiled once at module parse time — zero overhead per request
const SLUG_RE = /^[a-z0-9-]{3,80}$/;
const STATUS_LABELS: Record<number, string> = {
  200: 'OK',
  400: 'Bad Request',
  500: 'Internal Server Error',
};

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const slug = url.pathname.slice(1);

    if (!SLUG_RE.test(slug)) {
      return new Response('Invalid slug', { status: 400 });
    }

    return new Response(STATUS_LABELS[200]);
  },
};
```

## 4 — Detecting Stale Globals with Version Metadata Binding

Use the `CF-Worker-Version-Metadata` binding to invalidate module-scope caches when a new deployment rotates in, rather than serving stale compiled config.

```typescript
interface Env {
  CF_VERSION_METADATA: WorkerVersionMetadata;
}

let cachedVersion: string | null = null;
let cachedConfig: AppConfig | null = null;

async function getConfig(env: Env, kv: KVNamespace): Promise<AppConfig> {
  const currentVersion = env.CF_VERSION_METADATA.id;

  if (cachedVersion !== currentVersion || !cachedConfig) {
    const raw = await kv.get('app-config', 'json') as AppConfig;
    cachedConfig = raw;
    cachedVersion = currentVersion;
  }

  return cachedConfig!;
}
```

## 5 — Request-Scoped State (Never at Module Scope)

```typescript
// CORRECT — state lives in the handler's call stack
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Per-request accumulator — safe inside the handler
    const events: string[] = [];

    events.push(`start: ${Date.now()}`);
    const body = await request.text();
    events.push(`body-read: ${Date.now()}`);

    ctx.waitUntil(env.ANALYTICS.writeDataPoint({ blobs: events }));

    return new Response('ok');
  },
};
```

## 6 — Module-Scope Cache with TTL for Secrets Rotation

When a secret rotates, an isolate with a cached copy will serve the old secret until it is evicted. Implement a TTL on the cached value.

```typescript
interface CachedSecret { value: string; expiresAt: number; }

let _secret: CachedSecret | null = null;
const SECRET_TTL_MS = 5 * 60 * 1000; // 5 minutes

async function getApiSecret(store: SecretsStore): Promise<string> {
  const now = Date.now();
  if (_secret && _secret.expiresAt > now) return _secret.value;

  const value = await store.get('api-signing-key');
  if (!value) throw new Error('Secret not found');

  _secret = { value, expiresAt: now + SECRET_TTL_MS };
  return value;
}
```

## Anti-patterns

- **Storing `request.headers`, `request.url`, or authenticated user data at module scope** — data leaks across requests; a subsequent user sees the previous user's data.
- **Unconditional `await` at top level in module body** — Workers do not support async module evaluation; the import fails or hangs. Use lazy async init guarded by `null` check.
- **Never invalidating a module-scope cache** — secrets, feature flags, or config that rotate in KV/SecretsStore will be stuck until the isolate is evicted (potentially hours).
- **Assuming module-scope state is shared across all Worker instances** — each isolate is independent; mutable globals are per-isolate, not global across the fleet.

## Gotchas

- A single isolate handles requests **sequentially** (JavaScript is single-threaded), so mutable globals are safe from concurrent writes within one isolate, but are not shared across isolates running on different Cloudflare PoPs or even different instances at the same PoP.
- Isolate eviction is invisible to the Worker; there is no lifecycle hook for teardown. Cleanup (flushing buffers, closing sockets) must happen inside `ctx.waitUntil()` on each request.
- `wrangler dev` restarts the isolate on each file save; the "warm" module-scope state you see in production does not persist in local development.
- Memory-intensive module-scope caches accelerate the OOM eviction cycle — keep cached objects lean; large blobs belong in KV or R2, not in-process.
- `WorkerVersionMetadata` binding is available in module syntax Workers only; it is not available in Service Worker syntax.

## Verification

```typescript
// Confirm singleton is reused: counter should equal request number, not always 1
let requestCount = 0;

export default {
  async fetch(): Promise<Response> {
    requestCount++;
    return new Response(String(requestCount));
  },
};
// curl the Worker several times — responses should be 1, 2, 3, … while
// the same isolate is alive. A new isolate resets to 1.
```

## Related

- `workers-binding-rotation-and-global-scope-safety.md`
- `workers-version-metadata-deployment-correlation.md`
- `cloudflare-workers-secrets-store-rotation-automation.md`
- `workers-resource-limits.md`
- `workers-best-practices.md`

## Sources

- https://developers.cloudflare.com/workers/reference/security-model/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/version-metadata/
- https://developers.cloudflare.com/workers/observability/
- https://developers.cloudflare.com/workers/configuration/compatibility-flags/
