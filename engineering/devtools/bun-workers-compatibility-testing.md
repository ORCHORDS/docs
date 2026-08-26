# Bun Runtime Workers Compatibility Testing

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You develop Cloudflare Workers but want to run unit tests with Bun for its speed
advantage — sub-100ms cold starts vs. ~500ms for Node + Vitest. The problem is that
Workers globals (`Request`, `Response`, `Headers`, `caches`, `crypto`, `KVNamespace`)
behave subtly differently between the Bun runtime and the Workers runtime. You need a
strategy that lets fast Bun tests cover pure business logic while the Workers-specific
surface is covered by the dedicated `@cloudflare/vitest-pool-workers` suite.

## Context

Bun ≥ 1.1 ships Web API globals that are close enough to the Workers runtime for
testing pure functions, hono route handlers, schema validation, and serialization.
It does NOT emulate Workers-specific APIs (`waitUntil`, `KVNamespace`, `D1Database`,
Durable Objects, `WebSocketPair`). The pattern here is a two-tier test setup: Bun for
fast pure tests, Workers pool for integration tests.

Dependencies: `bun@^1.1`, `vitest@^2`, `@cloudflare/workers-types@^4`.

---

## 1. Marking test files by tier

```
tests/
  unit/          ← runs under Bun (fast)
    auth.test.ts
    schema.test.ts
    serializers.test.ts
  integration/   ← runs under @cloudflare/vitest-pool-workers
    kv-worker.test.ts
    d1-worker.test.ts
```

## 2. Bun-compatible unit test with Workers globals

```typescript
// tests/unit/auth.test.ts
// No vitest imports — uses Bun's built-in test runner

import { describe, it, expect } from "bun:test";
import { validateBearerToken } from "../../src/auth.js";

// Bun ships TextEncoder, crypto.subtle, Response, Request natively
describe("validateBearerToken", () => {
  it("returns null for missing Authorization header", () => {
    const req = new Request("https://example.com/", {
      headers: {},
    });
    expect(validateBearerToken(req)).toBeNull();
  });

  it("returns the token string for a valid header", () => {
    const req = new Request("https://example.com/", {
      headers: { Authorization: "Bearer abc123" },
    });
    expect(validateBearerToken(req)).toBe("abc123");
  });

  it("verifies an HMAC signature using crypto.subtle", async () => {
    const secret = "my-secret";
    const encoder = new TextEncoder();
    const key = await crypto.subtle.importKey(
      "raw",
      encoder.encode(secret),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign", "verify"]
    );
    const sig = await crypto.subtle.sign("HMAC", key, encoder.encode("payload"));
    const valid = await crypto.subtle.verify("HMAC", key, sig, encoder.encode("payload"));
    expect(valid).toBe(true);
  });
});
```

## 3. Package.json scripts for two-tier testing

```json
{
  "scripts": {
    "test:unit": "bun test tests/unit/",
    "test:integration": "vitest run tests/integration/",
    "test": "bun run test:unit && bun run test:integration",
    "test:unit:watch": "bun test --watch tests/unit/"
  }
}
```

## 4. Type-safe shim for Workers-only globals in Bun tests

```typescript
// tests/unit/bun-workers-shim.ts
// Import this in tests that reference Workers types but not their implementations.
// Bun's built-ins satisfy most of the Web API surface; this file shims the gaps.

import type {} from "@cloudflare/workers-types";

// Bun ships a compatible `crypto` — workers-types expects `SubtleCrypto` on globalThis
// No shim needed; Bun's `crypto.subtle` satisfies the interface.

// Bun's `Response` and `Request` lack `cf` property — add a typed stub for tests
declare module "bun" {
  interface Request {
    cf?: IncomingRequestCfProperties;
  }
}

export {}; // make this a module
```

## 5. Detecting runtime in shared source code

```typescript
// src/runtime.ts
/**
 * Detects whether the current runtime is Cloudflare Workers.
 * Used by code that needs to gate on Workers-specific APIs.
 */
export function isWorkersRuntime(): boolean {
  // Workers sets navigator.userAgent to "Cloudflare-Workers"
  return (
    typeof navigator !== "undefined" &&
    navigator.userAgent === "Cloudflare-Workers"
  );
}

export function isBunRuntime(): boolean {
  return typeof Bun !== "undefined";
}
```

## 6. GitHub Actions — parallel test tiers

```yaml
# .github/workflows/test.yml
name: Test

on: [push, pull_request]

jobs:
  unit-bun:
    name: Unit tests (Bun)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: oven-sh/setup-bun@v2
        with:
          bun-version: latest
      - run: bun install --frozen-lockfile
      - run: bun test tests/unit/

  integration-workers:
    name: Integration tests (Workers pool)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm vitest run tests/integration/
```

## Anti-patterns

- Running integration tests (KV, D1, Durable Objects) under Bun — Bun does not emulate
  these bindings; tests will either throw or silently use the wrong implementation.
- Using `bun:test` globals (`expect`, `describe`) in files that are also picked up by
  Vitest — the two test APIs are not fully compatible; keep them in separate directories.
- Relying on `fetch` behavior being identical — Bun's `fetch` follows the WHATWG spec
  while Workers `fetch` respects `request.cf` and has different redirect handling.

## Gotchas

- Bun 1.1 uses V8 for `crypto.subtle` operations on some platforms and JavaScriptCore
  on others — results are identical but timing may differ slightly in benchmarks.
- `@cloudflare/workers-types` adds properties to the global `Request` interface via
  TypeScript declaration merging. In Bun tests these properties are typed but absent at
  runtime; accessing `request.cf` returns `undefined`, not an error.
- `bun test` does not support the `--pool` option used by Vitest Workers — do not
  attempt to run Miniflare through `bun test`.

## Verification

```bash
# Bun unit suite should complete in < 500 ms
bun test tests/unit/ --reporter=verbose

# Workers integration suite (Node + Miniflare)
pnpm vitest run tests/integration/ --reporter=verbose

# Check runtime detection
bun -e "import('./src/runtime.js').then(r => console.log('bun:', r.isBunRuntime()))"
```

## Related

- `vitest-workers-miniflare-testing-setup.md`
- `vitest-pool-workers-cloudflare-test-api.md`
- `typescript-cloudflare-workers-strict.md`

## Sources

- https://bun.sh/docs/test/writing
- https://developers.cloudflare.com/workers/testing/
- https://github.com/oven-sh/bun/issues?q=cloudflare+workers
