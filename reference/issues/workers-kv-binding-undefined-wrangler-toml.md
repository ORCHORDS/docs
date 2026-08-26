# KV Binding Returns undefined at Runtime: Binding Name Case Mismatch in wrangler.toml

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker crashes at runtime with one of the following errors when attempting to read or write to a KV namespace:

```
TypeError: Cannot read properties of undefined (reading 'get')
TypeError: env.MY_KV is not a function
TypeError: Cannot read properties of undefined (reading 'put')
```

Or, in TypeScript strict mode, the build fails:

```
error TS2339: Property 'myKv' does not exist on type 'Env'
error TS2339: Property 'MY_KV' does not exist on type 'Env'
```

The KV namespace exists on the Cloudflare dashboard. The `wrangler.toml` has a `kv_namespaces` entry. Yet at runtime `env.MY_KV` is `undefined`.

---

## Context

- **Runtime**: Cloudflare Workers
- **Feature**: KV (Workers KV) namespace binding
- **Tool**: Wrangler 3.x
- **TypeScript**: 5.x with `@cloudflare/workers-types`
- **Wrangler config**: `wrangler.toml`

---

## Root Cause

KV namespace bindings (and all Workers bindings) are **case-sensitive**. The `binding` key in `wrangler.toml` must match **exactly** the property name you use in code to access `env.<BINDING_NAME>`.

Common mismatches:

| `wrangler.toml` binding | Code access | Result |
|-------------------------|-------------|--------|
| `MY_KV` | `env.myKv` | `undefined` |
| `my_kv` | `env.MY_KV` | `undefined` |
| `MyKv` | `env.MY_KV` | `undefined` |
| `MY_KV` | `env.MY_KV` | ✓ Works |

Additionally, a mismatch between the `Env` TypeScript interface and the actual binding name causes type errors at build time but does not prevent runtime access (the binding is still injected by name from `wrangler.toml`). This means you can have a type-checked interface that references a different name than the actual binding — the code compiles but fails at runtime.

The binding name is set **exactly once** in `wrangler.toml` and injected into the Worker as a property on the `env` object with that exact name. There is no aliasing or normalization.

---

## Broken Code

```toml
# wrangler.toml — binding defined as MY_KV_STORE
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "MY_KV_STORE"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
preview_id = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
```

```typescript
// src/index.ts — BROKEN: wrong binding name used
interface Env {
  MY_KV: KVNamespace; // Mismatches wrangler.toml (MY_KV_STORE vs MY_KV)
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // env.MY_KV is undefined at runtime — binding is MY_KV_STORE, not MY_KV
    const value = await env.MY_KV.get('some-key'); // TypeError: Cannot read properties of undefined
    return new Response(value ?? 'not found');
  },
};
```

```typescript
// src/index.ts — BROKEN: camelCase vs SCREAMING_SNAKE_CASE
interface Env {
  myKvStore: KVNamespace; // camelCase — doesn't match MY_KV_STORE
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    await env.myKvStore.put('key', 'value'); // undefined.put() — TypeError
    return new Response('ok');
  },
};
```

```toml
# wrangler.toml — BROKEN: binding name has trailing space (invisible bug)
[[kv_namespaces]]
binding = "MY_KV " # trailing space — env["MY_KV "] not env["MY_KV"]
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

```typescript
// src/index.ts — BROKEN: Env interface correct but toml has space
interface Env {
  MY_KV: KVNamespace; // correct, but toml binding is "MY_KV " (with space)
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Fails because env property is "MY_KV " (with space), not "MY_KV"
    await env.MY_KV.put('key', 'value'); // TypeError
    return new Response('ok');
  },
};
```

---

## Fix

### Step 1 — Align binding name exactly

```toml
# wrangler.toml — FIXED
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "MY_KV_STORE"   # Canonical name — use SCREAMING_SNAKE_CASE for bindings
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
preview_id = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
```

```typescript
// src/index.ts — FIXED: Env interface matches wrangler.toml exactly
interface Env {
  MY_KV_STORE: KVNamespace; // Exact match — same case, same characters
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.searchParams.get('key') ?? 'default';

    if (request.method === 'PUT') {
      const value = await request.text();
      await env.MY_KV_STORE.put(key, value, { expirationTtl: 3600 });
      return new Response('stored', { status: 201 });
    }

    const value = await env.MY_KV_STORE.get(key);
    if (value === null) {
      return new Response('not found', { status: 404 });
    }
    return new Response(value);
  },
};
```

### Step 2 — Use wrangler-generated types for compile-time safety

```bash
# Generate TypeScript types from your wrangler.toml bindings
npx wrangler types
```

This creates `worker-configuration.d.ts` with an auto-generated `Env` interface:

```typescript
// worker-configuration.d.ts (auto-generated, do not edit)
interface Env {
  MY_KV_STORE: KVNamespace;
  // ... other bindings
}
```

```typescript
// src/index.ts — FIXED: import generated types, never write Env by hand
/// <reference types="./worker-configuration.d.ts" />

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // TypeScript now errors if you mistype env.MY_KV_STORE
    const value = await env.MY_KV_STORE.get('key');
    return new Response(value ?? 'not found');
  },
};
```

```bash
# Add to package.json scripts to regenerate types on every build
# package.json
```

```json
{
  "scripts": {
    "build": "wrangler types && tsc --noEmit",
    "dev": "wrangler types && wrangler dev",
    "deploy": "wrangler types && wrangler deploy"
  }
}
```

### Step 3 — Verify binding is injected at runtime

```typescript
// src/index.ts — debug helper
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (new URL(request.url).pathname === '/debug-bindings') {
      // Lists all binding names actually injected by the runtime
      const keys = Object.keys(env as Record<string, unknown>);
      return Response.json({ bindings: keys });
    }
    // ... normal handler
    return new Response('ok');
  },
};
```

```bash
# Check what bindings are actually present at runtime
curl https://my-worker.example.com/debug-bindings
# => {"bindings": ["MY_KV_STORE", "DB", ...]} — verify exact names
```

---

## Verification

```bash
# 1. Confirm wrangler.toml binding name
grep -A3 'kv_namespaces' wrangler.toml
# Should show: binding = "MY_KV_STORE"

# 2. Confirm code uses the same name
grep -r 'env\.' src/ | grep -i 'kv'
# Should show: env.MY_KV_STORE

# 3. Generate and check types
npx wrangler types
cat worker-configuration.d.ts | grep -A5 'interface Env'
# Should show MY_KV_STORE: KVNamespace

# 4. TypeScript compile check
npx tsc --noEmit
# Should pass with no errors

# 5. Local dev test
npx wrangler dev &
curl -X PUT 'http://localhost:8787/?key=test' -d 'hello'
# => stored
curl 'http://localhost:8787/?key=test'
# => hello

# 6. KV operations via CLI
npx wrangler kv key put --binding MY_KV_STORE test-key "test-value"
npx wrangler kv key get --binding MY_KV_STORE test-key
# => test-value
```

---

## Anti-patterns

- Writing the `Env` TypeScript interface by hand instead of using `wrangler types`.
- Using camelCase binding names in `wrangler.toml` (convention is SCREAMING_SNAKE_CASE for bindings).
- Copying binding names between files without checking case.
- Not running `wrangler types` as part of the build pipeline.
- Using a different binding name in `preview_id` vs `id` entries and expecting them to behave the same.

---

## Gotchas

- `wrangler types` regenerates `worker-configuration.d.ts` from the current `wrangler.toml` — running it after every `wrangler.toml` change prevents stale type drift.
- In local `wrangler dev`, KV bindings use a local on-disk store in `.wrangler/state/v3/kv/`. Data there is independent of the remote KV namespace.
- The `preview_id` is used during `wrangler dev` when connecting to a remote KV namespace with `--remote`. It should reference a separate preview KV namespace, not the production one.
- KV bindings defined in a `[env.staging]` block in `wrangler.toml` only apply when deploying with `--env staging`; the default deployment uses root-level bindings.
- Deleting a KV namespace from the Cloudflare dashboard does not remove the binding from `wrangler.toml` — the Worker will deploy but `env.MY_KV_STORE` will be `undefined` at runtime.

---

## Related

- `documentation/categories/issues/d1-wrangler-local-remote-binding-mismatch.md`
- `documentation/categories/issues/workers-durable-object-id-from-name-cross-script.md`
- `documentation/categories/issues/workers-ai-model-not-found-gateway-error.md`

---

## Sources

- https://developers.cloudflare.com/kv/api/
- https://developers.cloudflare.com/workers/wrangler/configuration/#kv-namespaces
- https://developers.cloudflare.com/workers/languages/typescript/#generate-types
- https://developers.cloudflare.com/kv/get-started/
- https://developers.cloudflare.com/workers/testing/local-development/
