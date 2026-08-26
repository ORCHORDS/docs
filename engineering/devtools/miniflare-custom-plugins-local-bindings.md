# Miniflare Custom Plugins and Local Bindings for Workers Testing

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your Cloudflare Worker depends on a binding that Miniflare does not support out of the box — a beta product, an internal platform service, or a third-party integration that only exists as a Workers binding. Running `wrangler dev` against production resources is too risky; unit tests using plain mocks miss the serialization and permission boundaries that the runtime enforces. You need a local simulation that behaves like the real binding but lives entirely on your machine.

---

## Context

Miniflare v3 (the engine used by `wrangler dev --local` and `@cloudflare/vitest-pool-workers`) exposes a plugin API that lets you register custom namespace factories. Each plugin can introduce a new binding type — with its own storage, method surface, and error semantics — that Workers code receives alongside built-in bindings such as KV and D1.

The plugin API sits in `miniflare`'s `MiniflareOptions` object and is separate from the Vitest pool. You can use it from:

- `vitest.config.ts` via `miniflare` option in `@cloudflare/vitest-pool-workers`
- A standalone `Miniflare` instance in custom test harnesses or CLI scripts
- `wrangler.toml` for local dev (Wrangler delegates binding resolution to Miniflare)

---

## 1. Installing the Right Packages

```bash
pnpm add -D miniflare @cloudflare/vitest-pool-workers vitest
```

Pin Miniflare to the same major version that `wrangler` depends on to avoid mismatched `workerd` binaries:

```jsonc
// package.json
{
  "devDependencies": {
    "miniflare": "^3.20240701.0",
    "@cloudflare/vitest-pool-workers": "^0.5.0",
    "wrangler": "^3.60.0"
  }
}
```

---

## 2. Understanding the Plugin Shape

A Miniflare plugin is a plain object conforming to `MiniflarePlugin`:

```typescript
import type { MiniflarePlugin, PluginContext } from "miniflare";

export const myPlugin: MiniflarePlugin = {
  // Unique string key that namespaces all bindings this plugin provides
  name: "MY_PLUGIN",

  // Called once during Miniflare initialisation. Return the options schema
  // that users can pass in MiniflareOptions.
  getOptions(options) {
    return {
      // Declare new top-level option keys here
      myBindings: options.myBindings ?? {},
    };
  },

  // Called whenever a new Worker script is being set up. Return bindings
  // (plain objects / Proxies) that the Worker receives.
  async getBindings(options, ctx: PluginContext) {
    const bindings: Record<string, unknown> = {};
    for (const [name, config] of Object.entries(options.myBindings ?? {})) {
      bindings[name] = buildMyBinding(config, ctx);
    }
    return bindings;
  },

  // Optional: perform cleanup when Miniflare is disposed.
  async dispose() {},
};
```

---

## 3. Writing a Custom Rate-Limiter Binding

The following simulates a `RATE_LIMITER` binding that mirrors the Cloudflare Rate Limiting API surface. It stores counters in memory, respecting a configurable window.

```typescript
// test/plugins/rate-limiter.plugin.ts
import type { MiniflarePlugin, PluginContext } from "miniflare";

interface RateLimiterConfig {
  limit: number;
  period: number; // seconds
}

function buildRateLimiter(cfg: RateLimiterConfig) {
  const counters = new Map<string, { count: number; windowStart: number }>();

  return {
    async limit(opts: { key: string }): Promise<{ success: boolean }> {
      const now = Date.now();
      const windowMs = cfg.period * 1000;
      const existing = counters.get(opts.key);

      if (!existing || now - existing.windowStart > windowMs) {
        counters.set(opts.key, { count: 1, windowStart: now });
        return { success: true };
      }

      if (existing.count >= cfg.limit) {
        return { success: false };
      }

      existing.count += 1;
      return { success: true };
    },
  };
}

export const rateLimiterPlugin: MiniflarePlugin = {
  name: "RATE_LIMITER_PLUGIN",

  getOptions(options: any) {
    return {
      rateLimiters: options.rateLimiters ?? {},
    };
  },

  async getBindings(options: any, _ctx: PluginContext) {
    const bindings: Record<string, unknown> = {};
    for (const [name, cfg] of Object.entries(
      (options.rateLimiters ?? {}) as Record<string, RateLimiterConfig>
    )) {
      bindings[name] = buildRateLimiter(cfg);
    }
    return bindings;
  },
};
```

---

## 4. Registering the Plugin in vitest.config.ts

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";
import { defineWorkersProject } from "@cloudflare/vitest-pool-workers/config";
import { rateLimiterPlugin } from "./test/plugins/rate-limiter.plugin";

export default defineWorkersProject({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          // Register custom plugins
          plugins: [rateLimiterPlugin],
          // Pass plugin-specific options
          rateLimiters: {
            // Binding name in Worker → config
            MY_RATE_LIMITER: { limit: 10, period: 60 },
          },
        },
      },
    },
  },
});
```

Your `wrangler.toml` declares the binding name but Miniflare resolves it locally through the plugin instead of making a remote call:

```toml
# wrangler.toml
[[unsafe.bindings]]
type = "ratelimit"
name = "MY_RATE_LIMITER"
namespace_id = "1001"
simple = { limit = 10, period = 60 }
```

---

## 5. Using the Binding in Worker Code

```typescript
// src/index.ts
export interface Env {
  MY_RATE_LIMITER: {
    limit(opts: { key: string }): Promise<{ success: boolean }>;
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const ip = request.headers.get("cf-connecting-ip") ?? "unknown";
    const { success } = await env.MY_RATE_LIMITER.limit({ key: ip });

    if (!success) {
      return new Response("Rate limit exceeded", { status: 429 });
    }

    return new Response("OK");
  },
};
```

---

## 6. Writing Tests Against the Custom Binding

```typescript
// test/rate-limiter.test.ts
import { describe, it, expect, beforeAll } from "vitest";
import { env, createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import worker from "../src/index";

describe("rate limiter", () => {
  it("allows requests under the limit", async () => {
    const request = new Request("https://example.com/", {
      headers: { "cf-connecting-ip": "1.2.3.4" },
    });
    const ctx = createExecutionContext();
    const response = await worker.fetch(request, env, ctx);
    await waitOnExecutionContext(ctx);
    expect(response.status).toBe(200);
  });

  it("blocks after exceeding the limit", async () => {
    const ip = "9.9.9.9";
    const ctx = createExecutionContext();

    // Exhaust the 10-request limit
    for (let i = 0; i < 10; i++) {
      await worker.fetch(
        new Request("https://example.com/", {
          headers: { "cf-connecting-ip": ip },
        }),
        env,
        ctx
      );
    }

    const blocked = await worker.fetch(
      new Request("https://example.com/", {
        headers: { "cf-connecting-ip": ip },
      }),
      env,
      ctx
    );
    await waitOnExecutionContext(ctx);
    expect(blocked.status).toBe(429);
  });
});
```

---

## 7. Simulating a Durable Object Stub Without a Real DO Class

When you want to test a Worker that _calls_ a Durable Object but you do not want to load the DO class, build a fake stub:

```typescript
// test/plugins/fake-do.plugin.ts
import type { MiniflarePlugin } from "miniflare";

interface FakeDoConfig {
  handler: (request: Request) => Promise<Response>;
}

export function makeFakeDoPlugin(
  bindingName: string,
  handler: (request: Request) => Promise<Response>
): MiniflarePlugin {
  return {
    name: `FAKE_DO_${bindingName}`,

    getOptions(options: any) {
      return { [`fakeDo_${bindingName}`]: options[`fakeDo_${bindingName}`] };
    },

    async getBindings(options: any) {
      const stub = {
        idFromName: (_name: string) => ({ toString: () => "fake-id" }),
        idFromString: (s: string) => ({ toString: () => s }),
        get: (_id: unknown) => ({
          fetch: handler,
        }),
      };
      return { [bindingName]: stub };
    },
  };
}
```

Register it in `vitest.config.ts`:

```typescript
plugins: [
  makeFakeDoPlugin("ROOM", async (req) => {
    const body = await req.json();
    return Response.json({ echo: body, fake: true });
  }),
],
```

---

## Anti-patterns

- **Returning a raw class instance as a binding** — Miniflare passes bindings through a structured-clone boundary in some modes; prefer plain objects with async methods.
- **Using Node.js APIs inside a plugin's binding implementation** — the binding's _methods_ run in Node.js, but make sure you do not accidentally import Node internals that break when the Worker code is compiled for `workerd`.
- **Sharing mutable state between plugin instances without reset** — each test file gets a fresh `Miniflare` context via the pool; if your plugin stores state globally across multiple `MiniflarePlugin` references, tests will bleed into each other.
- **Skipping `dispose`** — plugins that open TCP connections (e.g., to a local Redis) must close them in `dispose`, otherwise the Vitest process hangs.

---

## Gotchas

- The `plugins` array in `miniflare` options is ordered; if two plugins declare the same option key, the last one wins.
- `@cloudflare/vitest-pool-workers` re-creates the Miniflare instance between test _files_ but reuses it across tests within the same file. Reset any in-memory counters in `beforeEach` if isolation matters.
- Miniflare v3 resolves `[[unsafe.bindings]]` in `wrangler.toml` locally; the binding `type` must match what Miniflare knows. For custom types, omit `type` and rely solely on the plugin.
- When running `wrangler dev --local`, Miniflare picks up plugins only if you start it via the Miniflare JavaScript API, not the Wrangler CLI. For CLI usage, use `wrangler dev` with real remote resources or use Vitest for local simulation.

---

## Verification

```bash
# Run the custom-binding tests
pnpm vitest run

# Confirm binding is injected by inspecting the test output
pnpm vitest run --reporter=verbose 2>&1 | grep "rate limiter"

# Check the Miniflare version wrangler bundles
node -e "const {Miniflare} = require('miniflare'); console.log(Miniflare.prototype.constructor.name)"
```

---

## Related

- `vitest-workers-miniflare-testing-setup.md` — foundational Vitest + Miniflare setup
- `durable-objects-local-debugging.md` — debugging real Durable Objects locally
- `wrangler-dev-local-d1-r2-kv.md` — built-in binding emulation in wrangler dev

---

## Sources

- Miniflare Plugin API: https://miniflare.dev/developing/plugins
- Cloudflare Rate Limiting Workers API: https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
- `@cloudflare/vitest-pool-workers` docs: https://developers.cloudflare.com/workers/testing/vitest-integration/
- Miniflare GitHub source (`packages/miniflare/src/plugins`): https://github.com/cloudflare/workers-sdk/tree/main/packages/miniflare/src/plugins
