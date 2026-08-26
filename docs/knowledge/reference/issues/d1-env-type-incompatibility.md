# d1-env-type-incompatibility

**Issue:** Two Env interfaces — `types.Env` vs `auth.Env` — cause D1Database type incompatibility
**Date:** 2026-08-11
**Status:** documented

## Symptom

```
Argument of type 'Env' is not assignable to parameter of type 'import(".../auth").Env'.
  Types of property 'DB' are incompatible.
    Type '{ prepare: (q: string) => { bind: (...args: unknown[]) => { run: () => Promise<unknown> } } } | undefined'
    is not assignable to type 'D1Database | undefined'.
```

This happens when:
1. `_lib/auth.ts` imports `@cloudflare/workers-types` which gives `DB: D1Database`
2. `_lib/types.ts` defines its own `DB` type as an inline object type
3. A routing file using `types.Env` tries to call `handleSomething(request, env)` where
   the handler expects `auth.Env`

## Root cause

Hand-rolled inline types are not structurally compatible with `D1Database` (from workers-types)
even if they look similar. `D1Database` has additional methods and types that the inline
definition doesn't satisfy.

## Fix

Update `_lib/types.ts` to use the strict globals from `@cloudflare/workers-types`:

```typescript
// Before (hand-rolled inline types — incompatible):
export interface Env {
  DB?: {
    prepare: (q: string) => {
      bind: (...args: unknown[]) => {
        run: () => Promise<unknown>;
        all: () => Promise<{ results: unknown[] }>;
        first: () => Promise<unknown>;
      };
    };
  };
  RATE_LIMIT?: {
    get: (k: string) => Promise<string | null>;
    put: (k: string, v: string, opts?: { expirationTtl?: number }) => Promise<void>;
  };
}

// After (use strict workers-types globals directly):
export interface Env {
  DB?: D1Database;          // global from @cloudflare/workers-types
  RATE_LIMIT?: KVNamespace; // global from @cloudflare/workers-types
  SESSIONS?: KVNamespace;
}
```

`D1Database` and `KVNamespace` are injected as globals by `@cloudflare/workers-types` — no import needed.

## tsconfig requirement

Ensure `tsconfig.functions.json` includes `@cloudflare/workers-types`:

```json
{
  "compilerOptions": {
    "types": ["@cloudflare/workers-types"]
  }
}
```

Without this, `D1Database` and `KVNamespace` are `undefined` as types and the Env interface
fails to compile.

## Single Env interface rule

There must be EXACTLY ONE `Env` interface in the codebase, exported from `_lib/types.ts` (or `_lib/auth.ts`).
All other files import and use it — never redefine it locally.

Signs you have two:
- Type errors when passing `env` between files
- Import paths like `import type { Env } from '../../_lib/auth'` in some files
  and `import type { Env } from '../../_lib/types'` in others

## Detection

```bash
grep -rn "interface Env" functions/
# Should output exactly one file
```

If it outputs two files, merge them. The canonical location is `_lib/types.ts` and `_lib/auth.ts`
re-exports it, or vice versa — pick one and stick to it.

## Related

- `workers-types-migration.md`
- `pages-functions-env-types.md`
- `typescript-route-handler.md`
- `wrangler-toml-reference.md`
