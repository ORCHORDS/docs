# Workers Module-Scope Memoization Across Requests

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Worker re-derives the same expensive value on every request: parsing a large JSON
config blob fetched from KV, importing a crypto key from raw bytes stored in an
environment secret, constructing a compiled regular expression from a pattern string,
or resolving a Durable Object ID from a well-known name. The derivation is
deterministic within an isolate's lifetime and adds 1–5 ms per request unnecessarily.

The pattern is common after Workers module syntax (ESM) became the standard: because
module-level code runs once per isolate instantiation, variables declared at the top
level of a module persist across all requests handled by that isolate. This is
exploitable as a zero-cost, zero-infrastructure memoization layer.

## Context

A Cloudflare Workers isolate is a V8 isolate that is created when a Worker is first
invoked (cold start) and then reused for subsequent requests within the same PoP for
the lifetime of the isolate (typically minutes, up to the 30-second CPU idle eviction
threshold). Module-level `const` and `let` bindings survive between `fetch` handler
invocations within a single isolate.

**This is different from a global shared cache.** Each isolate is independent; module
scope is not shared across isolates or across PoPs. Treat it as an in-process cache
that amortizes initialization cost across the requests a single isolate handles,
typically dozens to hundreds before the isolate is evicted.

The Workers runtime does not expose an API to query how many requests an isolate has
handled, but the pattern is safe: every value derived from environment variables or
static secrets is stable for the isolate's lifetime.

## Basic Memoization Pattern

```typescript
// worker/crypto.ts

// Module-level cache — initialized once per isolate, persists across requests.
let cachedSigningKey: CryptoKey | null = null;

export async function getSigningKey(secret: string): Promise<CryptoKey> {
  if (cachedSigningKey !== null) return cachedSigningKey;

  const raw = new TextEncoder().encode(secret);
  cachedSigningKey = await crypto.subtle.importKey(
    "raw",
    raw,
    { name: "HMAC", hash: "SHA-256" },
    false,        // non-extractable
    ["sign", "verify"]
  );
  return cachedSigningKey;
}
```

```typescript
// worker/handler.ts
import { getSigningKey } from "./crypto";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // First request in this isolate: ~0.5 ms importKey call.
    // Subsequent requests: synchronous null-check, effectively free.
    const key = await getSigningKey(env.SIGNING_SECRET);
    // ... use key
  },
};
```

## Memoizing with a Promise (Avoiding the Double-Initialization Race)

When the first two concurrent requests arrive before the key import completes, the
naive `if (cached !== null)` guard allows both to start an `importKey`. The solution
is to cache the **Promise** itself, not the resolved value.

```typescript
// worker/crypto.ts
let signingKeyPromise: Promise<CryptoKey> | null = null;

export function getSigningKey(secret: string): Promise<CryptoKey> {
  if (signingKeyPromise !== null) return signingKeyPromise;

  signingKeyPromise = crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"]
  );
  return signingKeyPromise;
}
```

Now the first concurrent request creates the Promise; every subsequent request
(including others racing during that first request) receives the same Promise and
awaits the same resolution. `importKey` is called exactly once per isolate.

## Memoizing Parsed Config from KV

Fetching and JSON-parsing a large configuration object on every request wastes both
KV read quota and parsing time.

```typescript
// worker/config.ts
interface AppConfig {
  rateLimits: Record<string, number>;
  featureFlags: Record<string, boolean>;
  allowedOrigins: string[];
}

let configPromise: Promise<AppConfig> | null = null;
let configFetchedAt = 0;
const CONFIG_TTL_MS = 60_000; // Re-fetch after 1 minute even within the same isolate.

export function getConfig(env: Env): Promise<AppConfig> {
  const now = Date.now();
  if (configPromise !== null && now - configFetchedAt < CONFIG_TTL_MS) {
    return configPromise;
  }

  configFetchedAt = now;
  configPromise = env.CONFIG_KV.get("app-config", "json") as Promise<AppConfig>;
  return configPromise;
}
```

The TTL guard ensures that a long-lived isolate picks up updated config eventually.
Choose a TTL that balances freshness requirements against KV read cost.

## Memoizing Durable Object IDs

`idFromName` is a synchronous string-hash operation, but calling it on every request
within a hot path adds up. Module-scope maps avoid it entirely.

```typescript
// worker/do-ids.ts
const doIdCache = new Map<string, DurableObjectId>();

export function getDoId(env: Env, name: string): DurableObjectId {
  let id = doIdCache.get(name);
  if (id === undefined) {
    id = env.MY_DO.idFromName(name);
    doIdCache.set(name, id);
  }
  return id;
}
```

Note: `DurableObjectId` objects are safe to cache because they are value-semantic
(they encode the 64-bit ID as a hex string internally and are not bound to a
particular request's lifetime).

## Compiled Regular Expressions

V8 JIT-compiles regular expressions lazily; a complex regex compiled on the first
`new RegExp(...)` call may add 0.1–1 ms. Moving it to module scope makes it compile
once per isolate.

```typescript
// worker/validation.ts

// Compiled once at isolate initialization time.
const EMAIL_RE =
  /^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/;

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export function isValidEmail(s: string): boolean {
  return EMAIL_RE.test(s);
}

export function isValidSlug(s: string): boolean {
  return SLUG_RE.test(s);
}
```

## Anti-patterns

- **Caching request-scoped values**: Do not store anything derived from request
  headers, cookies, or body in module scope. It will bleed across requests and create
  security vulnerabilities.
- **Caching non-deterministic values without a TTL**: Tokens, timestamps, and random
  seeds change over time. Always pair them with a TTL or a version tag.
- **Assuming module scope is a distributed cache**: Module scope is per-isolate. Do
  not use it to coordinate state between Workers instances — that requires KV,
  Durable Objects, or another shared store.
- **Forgetting error handling in cached Promises**: If a cached Promise rejects, every
  subsequent caller gets the same rejection. Reset the cache variable on rejection so
  the next call retries.

```typescript
// Correct: reset on rejection so callers can retry.
export function getSigningKey(secret: string): Promise<CryptoKey> {
  if (signingKeyPromise !== null) return signingKeyPromise;

  signingKeyPromise = crypto.subtle
    .importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"])
    .catch((err) => {
      signingKeyPromise = null; // allow retry on next request
      throw err;
    });

  return signingKeyPromise;
}
```

## Gotchas

- **Isolate eviction resets module scope**: After a period of inactivity (or after
  a new Worker deployment), a fresh isolate starts with all module-scope variables at
  their initialization values. The first request always pays the derivation cost.
- **`wrangler dev` runs in Node.js, not V8**: Module scope in `wrangler dev` is shared
  across all requests in the dev server process, which is different from the isolate-
  per-PoP model in production. Test eviction behavior with `wrangler dev --remote`.
- **Module-scope initialization order**: ESM module initialization runs top-to-bottom.
  Avoid accessing `env` (which is only available inside the `fetch` handler) during
  module top-level execution. Use lazy initialization patterns (functions, not
  immediately-invoked top-level code) for anything that needs `env`.
- **Memory pressure**: A module-scope cache that grows unboundedly (e.g., a `Map`
  keyed on request-time user IDs) can inflate isolate memory. Bound all caches with
  an LRU eviction policy or a maximum size.

## Verification

Add a counter to confirm that initialization runs only once per isolate:

```typescript
let initCount = 0;
let keyPromise: Promise<CryptoKey> | null = null;

export function getKey(secret: string): Promise<CryptoKey> {
  if (keyPromise !== null) return keyPromise;
  initCount++;
  console.log(`[memoize] importKey call #${initCount} in this isolate`);
  keyPromise = crypto.subtle.importKey(/* ... */);
  return keyPromise;
}
```

Deploy to a staging Worker and issue #<number> rapid requests. The Workers Logs should show
`importKey call #1` exactly once per isolate instantiation (usually once total for a
low-traffic test) and no subsequent log lines.

## Related

- `workers-module-initialization-lazy-loading.md`
- `workers-cold-start-optimization.md`
- `workers-wasm-module-caching.md`
- `kv-metadata-only-reads-optimization.md`
- `workers-memory-allocation-optimization.md`

## Sources

- Cloudflare Workers runtime behavior: https://developers.cloudflare.com/workers/reference/how-workers-works/
- Workers module syntax: https://developers.cloudflare.com/workers/reference/migrate-to-module-workers/
- Web Crypto API: https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/importKey
