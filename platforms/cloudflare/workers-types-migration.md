# workers-types-migration

**Issue:** Migrating to @cloudflare/workers-types — D1Database/KVNamespace compatibility break
**Date:** 2026-08-11
**Status:** documented

## Symptom

Adding `"@cloudflare/workers-types"` to `tsconfig.json` `types` array suddenly produces
hundreds of TS errors across functions that compiled cleanly before:

```
error TS2739: Type '{ prepare: (q: string) => ... }' is missing properties from type 'D1Database'
error TS2345: Argument of type '{ get: ...; put: ...; }' is not assignable to parameter of type 'KVNamespace'
error TS2339: Property 'privateKey' does not exist on type 'CryptoKey | CryptoKeyPair'
error TS2345: Argument of type 'ArrayBuffer | JsonWebKey' is not assignable to parameter of type 'JsonWebKey'
```

## Root cause

Before adding workers-types, `env.DB` typed as `any` — structural mismatches invisible.
After adding workers-types, globals become strict:

- `env.DB: D1Database | undefined` — `D1Database.prepare()` returns `D1PreparedStatement` with many more methods than any inline interface you hand-wrote
- `env.RATE_LIMIT: KVNamespace` — richer than `{ get: ...; put: ... }`
- `crypto.subtle.generateKey()` returns `CryptoKey | CryptoKeyPair` — even when you pass `['sign', 'verify']` TS doesn't narrow automatically

If two files both define their own `Env` interface (common in large Pages Functions repos), the inline types in the "simple" file are no longer assignable to the strict types needed by the "auth" file.

## Fix

### 1. Update shared Env interfaces to use strict types

```typescript
// _lib/types.ts — was:
interface Env {
  DB?: { prepare: (q: string) => { bind: (...args: unknown[]) => { run: () => Promise<unknown> } } };
  RATE_LIMIT?: { get: (k: string) => Promise<string | null>; put: (...) => Promise<void> };
}

// Fix: use globals from workers-types (no import needed — they're global):
interface Env {
  DB?: D1Database;
  RATE_LIMIT?: KVNamespace;
}
```

### 2. Non-null assert env.DB everywhere

```typescript
// Before (was fine with any):
await env.DB.prepare(sql).bind(...params).run();

// After (DB is D1Database | undefined):
await env.DB!.prepare(sql).bind(...params).run();
```

Batch fix with PowerShell: `(Get-Content file -Raw) -replace 'env\.DB\.', 'env.DB!.' | Set-Content file -NoNewline`

### 3. Cast crypto.subtle results

```typescript
// generateKey returns CryptoKey | CryptoKeyPair — narrow manually:
const keypair = await crypto.subtle.generateKey(
  { name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1,0,1]), hash: 'SHA-256' },
  true,
  ['sign', 'verify'],
) as CryptoKeyPair;  // <-- explicit cast

// exportKey returns ArrayBuffer | JsonWebKey — narrow for 'jwk':
const jwk = await crypto.subtle.exportKey('jwk', keypair.privateKey) as JsonWebKey;
```

### 4. `D1PreparedStatement.all()` typing

```typescript
// Typed results — pass generic:
const rows = await env.DB!.prepare(sql).bind(...params).all<{ id: string; name: string }>();
// rows.results is Array<{ id: string; name: string }>

// first() with generic:
const row = await env.DB!.prepare(sql).bind(id).first<{ id: string; email: string }>();
// row is { id: string; email: string } | null
```

### 5. Resolve Env incompatibility across files

When two files define separate `Env` interfaces and one passes `env` to functions expecting the other:

```typescript
// Option A: import and re-export from a single source
// _lib/types.ts:
export type { Env } from './_lib/auth';  // one canonical Env

// Option B: make the shared Env a superset
// Use D1Database/KVNamespace in BOTH files
```

## Verification

```bash
npx tsc -p tsconfig.functions.json --noEmit
# Must exit 0 (no output)
```

## Gotchas

- `skipLibCheck: true` skips `.d.ts` checking but NOT your own `.ts` files — errors in source still surface
- Adding workers-types exposes ALL pre-existing type errors that were hidden behind `any` — expect a large first-pass error count (we saw 2619 → 0 over iterative fixes)
- `D1PreparedStatement.batch()` is still broken by esbuild in Pages Functions — use sequential `.run()` calls (see `d1-batch-bundler-bug.md`)
- `DurableObjectNamespace`, `R2Bucket`, `EmailMessage` also become strict globals — check any `declare const` stubs in your files

## Related

- `d1-batch-bundler-bug.md`
- `d1-best-practices.md`
- `pages-best-practices.md`
- `kv-best-practices.md`
