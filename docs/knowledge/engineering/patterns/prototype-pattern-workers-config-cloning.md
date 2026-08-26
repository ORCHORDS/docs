# Prototype Pattern — Workers Config Cloning

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A multi-tenant Worker reads a base configuration from KV or D1 at startup and then
needs a per-request variant: a tenant override layered on the base, a locale-specific
copy, or a request-scoped copy that a middleware chain mutates without affecting other
concurrent requests. Reaching for `JSON.parse(JSON.stringify(base))` is error-prone
for typed configs, and `Object.assign` produces shallow copies that share nested
references across requests — a subtle concurrency bug in a Worker handling hundreds of
requests on the same isolate.

## Context

The Prototype pattern creates new objects by cloning an existing instance rather than
constructing from scratch. In a Worker the module-scope "prototype" is an immutable
base config loaded once; each request gets a typed deep clone via a dedicated `clone()`
method. Tenant overrides are applied to the clone, never to the base. Because Workers
are single-threaded within an isolate but handle requests that interleave across
microtask checkpoints, shared mutable module-scope state is a real hazard — the
Prototype makes the per-request copy explicit and typed.

## Cloneable Config Type

Define the config as a class with a `clone()` method so TypeScript enforces the shape.

```typescript
// config/worker-config.ts

export interface RateLimitPolicy {
  requestsPerMinute: number;
  burstSize: number;
}

export interface CorsPolicy {
  allowedOrigins: string[];
  allowCredentials: boolean;
  maxAgeSec: number;
}

export interface FeatureFlags {
  betaSearch: boolean;
  streamingResponses: boolean;
}

export class WorkerConfig {
  constructor(
    public readonly tenantId: string,
    public readonly rateLimit: RateLimitPolicy,
    public readonly cors: CorsPolicy,
    public readonly features: FeatureFlags,
    public readonly upstreamUrl: string,
  ) {}

  /** Deep clone — safe to mutate on the returned instance. */
  clone(): WorkerConfig {
    return new WorkerConfig(
      this.tenantId,
      { ...this.rateLimit },
      { ...this.cors, allowedOrigins: [...this.cors.allowedOrigins] },
      { ...this.features },
      this.upstreamUrl,
    );
  }

  /** Clone and apply a partial tenant override in one step. */
  withOverrides(overrides: Partial<{
    rateLimit: Partial<RateLimitPolicy>;
    cors: Partial<CorsPolicy>;
    features: Partial<FeatureFlags>;
    upstreamUrl: string;
  }>): WorkerConfig {
    const next = this.clone();
    return new WorkerConfig(
      next.tenantId,
      { ...next.rateLimit, ...overrides.rateLimit },
      { ...next.cors, ...overrides.cors,
        allowedOrigins: overrides.cors?.allowedOrigins ?? [...next.cors.allowedOrigins] },
      { ...next.features, ...overrides.features },
      overrides.upstreamUrl ?? next.upstreamUrl,
    );
  }
}
```

## Base Config Loader (module scope)

Load once per isolate cold start; freeze the result so callers must clone before
mutating.

```typescript
// config/loader.ts
import { WorkerConfig } from './worker-config';

let baseConfig: Readonly<WorkerConfig> | null = null;

export async function getBaseConfig(kv: KVNamespace): Promise<Readonly<WorkerConfig>> {
  if (baseConfig) return baseConfig;

  const raw = await kv.get('config:base', 'json') as {
    rateLimit: { requestsPerMinute: number; burstSize: number };
    cors: { allowedOrigins: string[]; allowCredentials: boolean; maxAgeSec: number };
    features: { betaSearch: boolean; streamingResponses: boolean };
    upstreamUrl: string;
  } | null;

  if (!raw) throw new Error('Base config not found in KV');

  baseConfig = Object.freeze(
    new WorkerConfig('__base__', raw.rateLimit, raw.cors, raw.features, raw.upstreamUrl),
  );
  return baseConfig;
}

/** Call this in tests or on config change events to bust the module-scope cache. */
export function resetBaseConfig(): void {
  baseConfig = null;
}
```

## Tenant Override Loader

Load a sparse tenant override from KV and merge it onto a clone of the base.

```typescript
// config/tenant.ts
import { WorkerConfig } from './worker-config';
import { getBaseConfig } from './loader';

export async function getConfigForTenant(
  kv: KVNamespace,
  tenantId: string,
): Promise<WorkerConfig> {
  const base = await getBaseConfig(kv);
  const override = await kv.get(`config:tenant:${tenantId}`, 'json') as Partial<{
    rateLimit: Partial<{ requestsPerMinute: number; burstSize: number }>;
    cors: Partial<{ allowedOrigins: string[]; allowCredentials: boolean; maxAgeSec: number }>;
    features: Partial<{ betaSearch: boolean; streamingResponses: boolean }>;
    upstreamUrl: string;
  }> | null;

  if (!override) {
    // Clone base so downstream middleware can annotate safely
    return new WorkerConfig(
      tenantId,
      { ...base.rateLimit },
      { ...base.cors, allowedOrigins: [...base.cors.allowedOrigins] },
      { ...base.features },
      base.upstreamUrl,
    );
  }

  return base.withOverrides(override);
}
```

## Worker Entry Point

Each request gets its own config clone; mutations in middleware don't leak.

```typescript
// worker.ts
import { getConfigForTenant } from './config/tenant';

export interface Env {
  CONFIG: KVNamespace;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const tenantId = req.headers.get('x-tenant-id') ?? 'default';
    const cfg      = await getConfigForTenant(env.CONFIG, tenantId);

    // Middleware can safely annotate cfg without affecting module-scope base
    if (req.headers.get('x-beta-user') === '1') {
      // withOverrides returns a new instance — original cfg unchanged
      const betaCfg = cfg.withOverrides({ features: { betaSearch: true, streamingResponses: cfg.features.streamingResponses } });
      return handleRequest(req, betaCfg);
    }

    return handleRequest(req, cfg);
  },
};

async function handleRequest(req: Request, cfg: WorkerConfig): Promise<Response> {
  const upstreamReq = new Request(cfg.upstreamUrl + new URL(req.url).pathname, req);

  if (cfg.features.streamingResponses) {
    upstreamReq.headers.set('accept', 'text/event-stream');
  }

  return fetch(upstreamReq);
}
```

## Config KV Shape

```json
// config:base
{
  "rateLimit":   { "requestsPerMinute": 100, "burstSize": 20 },
  "cors":        { "allowedOrigins": ["https://app.example.com"], "allowCredentials": true, "maxAgeSec": 86400 },
  "features":    { "betaSearch": false, "streamingResponses": false },
  "upstreamUrl": "https://api.internal.example.com"
}

// config:tenant:acme
{
  "rateLimit": { "requestsPerMinute": 500 },
  "features":  { "betaSearch": true }
}
```

## Anti-patterns

- **Shallow Object.assign at call site** — `const cfg = Object.assign({}, baseConfig)`
  copies top-level keys but nested objects like `cors.allowedOrigins` remain shared.
  Any push to the array in one request leaks into all subsequent requests.
- **Mutating module-scope config** — Because Workers are single-threaded but
  non-blocking, a mutation before an `await` and another mutation after it in a
  different logical request can interleave. Always clone before mutating.
- **Cloning in the hot path on every subrequest** — Clone once per Worker invocation,
  not once per upstream fetch call inside the handler.

## Gotchas

- `Object.freeze` on the base config only shallow-freezes. A nested array like
  `allowedOrigins` is still mutable. Use `clone()` as the only path to a mutable
  config copy; don't rely on freeze for deep immutability.
- KV `get` with `'json'` returns `null` on a miss, not an empty object. Always guard
  with `?? null` and fall back to the base.
- If config changes frequently (< 60 s TTL), don't cache at module scope. Use a
  time-bounded cache keyed by a version hash stored alongside the config in KV.

## Verification

```typescript
import { WorkerConfig } from './config/worker-config';

const base = new WorkerConfig(
  'base',
  { requestsPerMinute: 100, burstSize: 20 },
  { allowedOrigins: ['https://a.com'], allowCredentials: true, maxAgeSec: 3600 },
  { betaSearch: false, streamingResponses: false },
  'https://api.example.com',
);

const clone = base.clone();
clone.cors.allowedOrigins.push('https://b.com');

// Confirm prototype is unmodified
console.assert(base.cors.allowedOrigins.length === 1, 'base must not be mutated');
console.assert(clone.cors.allowedOrigins.length === 2, 'clone should have new origin');

const tenant = base.withOverrides({ rateLimit: { requestsPerMinute: 500 } });
console.assert(tenant.rateLimit.requestsPerMinute === 500);
console.assert(base.rateLimit.requestsPerMinute   === 100, 'base still unchanged');
```

## Related

- `lazy-init-module-cache-workers.md` — caching the base prototype at module scope
- `builder-pattern-workers-response-construction.md` — building objects incrementally
- `memento-pattern-durable-objects-state-snapshot.md` — snapshotting mutable state

## Sources

- GoF *Design Patterns* (1994) — Prototype, pp. 117–126
- Cloudflare Workers execution context: https://developers.cloudflare.com/workers/reference/how-workers-works/
- KV namespace API: https://developers.cloudflare.com/kv/api/read-key-value-pairs/
