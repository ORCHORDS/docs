# Vitest Custom Matchers for Workers Environment

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Testing Cloudflare Workers responses with generic `expect` assertions produces verbose, hard-to-read tests. Rewriting the same header and status checks across hundreds of test files creates maintenance overhead when Workers-specific response shapes change. Custom Vitest matchers encapsulate Workers runtime idioms into expressive, reusable assertions that read as plain English in failure diffs.

## Context

Vitest exposes `expect.extend()` to register project-wide custom matchers. In a Workers test environment using `@cloudflare/vitest-pool-workers`, the test process runs inside the actual Workers runtime, so `Request`, `Response`, `Headers`, and `URL` are the real globals — not polyfills. Custom matchers can therefore leverage native Workers behaviour to assert on CORS headers, cache directives, content negotiation, and JSON shapes without repeating boilerplate across every spec. Registering matchers in `setupFiles` makes them available across all test files without explicit imports.

## Defining the Matchers Module

```typescript
// test/matchers/workers.ts
import type { MatcherState } from "vitest";

export interface WorkersMatchers<R = unknown> {
  toHaveStatus(status: number): R;
  toHaveHeader(name: string, value?: string | RegExp): R;
  toBeCorsResponse(origin?: string): R;
  toHaveCacheControl(directive: string): R;
  toBeJsonResponse<T = unknown>(schema?: (body: T) => boolean): R;
}

declare module "vitest" {
  interface Assertion<T = unknown> extends WorkersMatchers<T> {}
  interface AsymmetricMatchersContaining extends WorkersMatchers {}
}

export const workersMatchers: Parameters<typeof expect.extend>[0] = {
  toHaveStatus(this: MatcherState, received: Response, expected: number) {
    const pass = received.status === expected;
    return {
      pass,
      message: () =>
        `expected response status ${this.utils.printReceived(received.status)} ` +
        `to${pass ? " not" : ""} equal ${this.utils.printExpected(expected)}`,
    };
  },

  toHaveHeader(
    this: MatcherState,
    received: Response | Request,
    name: string,
    value?: string | RegExp
  ) {
    const actual = received.headers.get(name.toLowerCase());
    const present = actual !== null;
    const matches =
      value === undefined
        ? present
        : value instanceof RegExp
        ? present && value.test(actual!)
        : actual === value;
    return {
      pass: matches,
      message: () => {
        const got = actual ?? "(absent)";
        return (
          `expected header ${this.utils.printExpected(name)} ` +
          `${matches ? "not " : ""}to match — got ${this.utils.printReceived(got)}`
        );
      },
    };
  },

  toBeCorsResponse(this: MatcherState, received: Response, origin = "*") {
    const acao = received.headers.get("access-control-allow-origin");
    const pass = acao === origin || acao === "*";
    return {
      pass,
      message: () =>
        `expected CORS header Access-Control-Allow-Origin to be ` +
        `${this.utils.printExpected(origin)}, got ${this.utils.printReceived(acao)}`,
    };
  },

  toHaveCacheControl(this: MatcherState, received: Response, directive: string) {
    const cc = received.headers.get("cache-control") ?? "";
    const pass = cc.includes(directive);
    return {
      pass,
      message: () =>
        `expected Cache-Control ${this.utils.printReceived(cc)} ` +
        `to${pass ? " not" : ""} contain ${this.utils.printExpected(directive)}`,
    };
  },

  async toBeJsonResponse(
    this: MatcherState,
    received: Response,
    schema?: (body: unknown) => boolean
  ) {
    const ct = received.headers.get("content-type") ?? "";
    const isJson = ct.includes("application/json");
    if (!isJson) {
      return {
        pass: false,
        message: () =>
          `expected Content-Type application/json, got ${this.utils.printReceived(ct)}`,
      };
    }
    if (schema) {
      const body = await received.clone().json();
      const pass = schema(body);
      return {
        pass,
        message: () =>
          `expected response body to satisfy schema, got ${this.utils.printReceived(body)}`,
      };
    }
    return { pass: true, message: () => "expected response not to be JSON" };
  },
};
```

## Registering Matchers in Vitest Config

```typescript
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    setupFiles: ["./test/setup.ts"],
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
      },
    },
  },
});
```

```typescript
// test/setup.ts
import { expect } from "vitest";
import { workersMatchers } from "./matchers/workers";

expect.extend(workersMatchers);
```

## Using Custom Matchers in Tests

```typescript
// test/api.spec.ts
import { createExecutionContext, waitOnExecutionContext, env } from "cloudflare:test";
import { describe, it, expect } from "vitest";
import worker from "../src/index";

describe("GET /api/items", () => {
  it("returns a CORS-enabled JSON response with 200", async () => {
    const req = new Request("https://example.com/api/items", {
      headers: { Origin: "https://app.example.com" },
    });
    const ctx = createExecutionContext();
    const res = await worker.fetch(req, env, ctx);
    await waitOnExecutionContext(ctx);

    expect(res).toHaveStatus(200);
    await expect(res).toBeJsonResponse(
      (body: unknown) => Array.isArray((body as { items: unknown[] }).items)
    );
    expect(res).toBeCorsResponse("https://app.example.com");
    expect(res).toHaveCacheControl("no-store");
  });

  it("returns 401 with a WWW-Authenticate challenge when no token is supplied", async () => {
    const req = new Request("https://example.com/api/items");
    const ctx = createExecutionContext();
    const res = await worker.fetch(req, env, ctx);
    await waitOnExecutionContext(ctx);

    expect(res).toHaveStatus(401);
    expect(res).toHaveHeader("www-authenticate", /Bearer/);
  });
});
```

## Anti-patterns

- Asserting on `res.headers.get("Content-Type")` directly in every test instead of using `toBeJsonResponse` — breaks silently when a charset suffix changes
- Calling `res.json()` in the test body before a body-reading matcher runs — `Response.body` is a `ReadableStream` and can only be consumed once; the matcher must `clone()` internally
- Registering matchers inside individual `describe` blocks rather than `setupFiles` — they become invisible to other test files and produce misleading `is not a function` errors

## Gotchas

- `expect.extend()` in `setupFiles` runs once per Vitest worker thread; in sharded runs each shard resolves `setupFiles` relative to its own cwd, so use absolute paths or a workspace-rooted alias
- The `toBeJsonResponse` matcher is `async` because it reads the cloned body; callers must `await expect(res).toBeJsonResponse(...)` or the schema check resolves after the test exits without failing
- TypeScript augmentation of `vitest`'s `Assertion` interface must be in a file included by `tsconfig.json`'s `include` glob; a file sitting only under `node_modules` or outside the compilation root will not extend the type

## Verification

```bash
npx vitest run --reporter=verbose test/api.spec.ts
# Custom matcher names appear in failure diffs, not raw .status / .headers property checks

npx tsc --noEmit
# WorkersMatchers augmentation resolves without TS2339 errors on expect(res).toHaveStatus(...)
```

## Related

- `testing/vitest-cloudflare-pool-workers.md`
- `testing/workers-service-bindings-vitest-testing.md`
- `testing/workers-unit-testing-fetch-mocking.md`

## Sources

- https://vitest.dev/guide/extending-matchers
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://jestjs.io/docs/expect#expectextendmatchers
