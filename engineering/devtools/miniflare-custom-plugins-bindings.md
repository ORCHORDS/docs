# Miniflare Custom Plugins and Bindings for Local Testing

- Date: 2026-08-22
- Author: example.com
- Status: production

---

## Symptom / Use-case

You're testing a Cloudflare Worker locally and need bindings that Miniflare doesn't support out of the box — a third-party AI gateway, an internal service over Service Bindings, a custom environment variable loader, or a mock of a Cloudflare product still in private beta. Miniflare's plugin system and the `miniflare` npm package's programmatic API let you inject arbitrary bindings, intercept service calls, and simulate any runtime environment your Worker expects.

Typical scenarios:
- Mocking a Service Binding that calls another Worker in a monorepo during unit tests
- Injecting a fake `AI` binding (Cloudflare AI Gateway) for offline testing
- Providing a custom `QUEUE` binding that records messages instead of sending them
- Simulating rate-limit or quota errors from a binding to test error-handling paths
- Running Worker tests in CI without any Cloudflare credentials

---

## Context

Miniflare 3 (used internally by Wrangler 3 and Vitest's `@cloudflare/vitest-pool-workers`) runs Workers in a local V8 isolate using `workerd` — Cloudflare's open-source runtime. Unlike Miniflare 2, which shimmed bindings in Node.js, Miniflare 3 embeds the actual runtime, making local behavior much closer to production.

Custom bindings are injected in two ways:

1. **`bindings` option** — simple key/value pairs injected as environment variables (strings, objects, or plain functions). Used for lightweight mocks that don't need to be proper Cloudflare types.

2. **Miniflare Plugins** — plugins extend Miniflare's configuration schema and can register binding factories that produce proper `workerd`-compatible binding stubs. Used when the binding needs to behave like a real Cloudflare binding (e.g., with proper TypeScript types and async behavior).

---

## Setup: Miniflare Programmatic API

Install Miniflare as a direct dependency for programmatic use in tests:

```bash
pnpm add -D miniflare @cloudflare/workers-types wrangler
```

The `miniflare` package exposes a class that takes the same configuration as `wrangler.toml` plus additional options for custom bindings:

```typescript
// test/setup.ts
import { Miniflare } from 'miniflare';

const mf = new Miniflare({
  // Point at your Worker source (TypeScript is bundled automatically)
  scriptPath: 'src/index.ts',
  modules: true,

  // Standard bindings from wrangler.toml
  compatibilityDate: '2026-01-01',
  compatibilityFlags: ['nodejs_compat'],

  // D1 and KV bindings (local, in-memory)
  d1Databases: ['DB'],
  kvNamespaces: ['KV'],
  r2Buckets: ['BUCKET'],
});

// Each test gets a fresh env
const env = await mf.getBindings();
```

---

## Injecting Custom Object Bindings

The `bindings` option accepts arbitrary values. For simple mocks, inject plain objects that implement the binding's interface:

```typescript
// test/mocks/queue-mock.ts
export interface QueueMessage<T = unknown> {
  body: T;
  timestamp: Date;
}

export class MockQueue<T = unknown> {
  readonly messages: QueueMessage<T>[] = [];

  async send(body: T): Promise<void> {
    this.messages.push({ body, timestamp: new Date() });
  }

  async sendBatch(messages: Array<{ body: T }>): Promise<void> {
    for (const msg of messages) {
      await this.send(msg.body);
    }
  }

  clear(): void {
    this.messages.length = 0;
  }
}
```

```typescript
// test/worker.test.ts
import { Miniflare } from 'miniflare';
import { MockQueue } from './mocks/queue-mock';
import { describe, it, expect, beforeAll, afterAll } from 'vitest';

describe('Worker with Queue binding', () => {
  let mf: Miniflare;
  let mockQueue: MockQueue<{ userId: string; event: string }>;

  beforeAll(async () => {
    mockQueue = new MockQueue();

    mf = new Miniflare({
      scriptPath: 'src/index.ts',
      modules: true,
      compatibilityDate: '2026-01-01',
      bindings: {
        // Inject mock instead of real Queue binding
        EVENTS: mockQueue,
        // Simple value bindings
        ENVIRONMENT: 'test',
        MAX_RETRY_ATTEMPTS: '3',
      },
      d1Databases: ['DB'],
    });
  });

  afterAll(async () => {
    await mf.dispose();
  });

  it('enqueues an event when a user is created', async () => {
    mockQueue.clear();

    const response = await mf.dispatchFetch('http://localhost/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Alice', email: 'alice@test.com' }),
    });

    expect(response.status).toBe(201);
    expect(mockQueue.messages).toHaveLength(1);
    expect(mockQueue.messages[0].body).toMatchObject({
      event: 'user.created',
    });
  });
});
```

---

## Mocking Service Bindings

Service Bindings connect Workers to each other. In local tests, mock them as objects that implement the `Fetcher` interface:

```typescript
// test/mocks/service-mock.ts
export function createServiceMock(
  handler: (request: Request) => Response | Promise<Response>
): Fetcher {
  return {
    fetch: (input: RequestInfo | URL, init?: RequestInit) => {
      const request = new Request(input, init);
      return Promise.resolve(handler(request));
    },
    connect: () => {
      throw new Error('TCP connect not supported in mock');
    },
  };
}
```

```typescript
// test/worker.test.ts
import { createServiceMock } from './mocks/service-mock';

const authServiceMock = createServiceMock((request) => {
  const token = request.headers.get('Authorization');
  if (token === 'Bearer valid-token') {
    return Response.json({ userId: 'user-123', valid: true });
  }
  return Response.json({ valid: false }, { status: 401 });
});

const mf = new Miniflare({
  scriptPath: 'src/index.ts',
  modules: true,
  compatibilityDate: '2026-01-01',
  serviceBindings: {
    // Miniflare routes calls to AUTH_SERVICE to this mock
    AUTH_SERVICE: authServiceMock,
  },
});
```

---

## Miniflare Plugins (Advanced)

For bindings that need to integrate more deeply with the Miniflare/workerd lifecycle — persisting state, simulating Cloudflare-specific error codes, or providing a binding that requires a background process — write a Miniflare plugin.

Note: Miniflare 3's plugin API is internal and subject to change. Use `bindings` injection for most cases; reserve plugins for unavoidable edge cases.

```typescript
// test/plugins/analytics-plugin.ts
// A plugin that provides a mock Analytics Engine binding
import type { Plugin } from 'miniflare';

export interface AnalyticsEvent {
  blobs: string[];
  doubles: number[];
  indexes: string[];
}

export class MockAnalyticsDataset {
  readonly events: AnalyticsEvent[] = [];

  writeDataPoint(event: AnalyticsEvent): void {
    this.events.push(event);
  }

  getEvents(): AnalyticsEvent[] {
    return [...this.events];
  }

  clear(): void {
    this.events.length = 0;
  }
}

// Export a factory so tests can share the mock instance
export function createAnalyticsPlugin(): {
  dataset: MockAnalyticsDataset;
  binding: MockAnalyticsDataset;
} {
  const dataset = new MockAnalyticsDataset();
  return { dataset, binding: dataset };
}
```

```typescript
// test/worker.test.ts
import { Miniflare } from 'miniflare';
import { createAnalyticsPlugin } from './plugins/analytics-plugin';

const { dataset, binding } = createAnalyticsPlugin();

const mf = new Miniflare({
  scriptPath: 'src/index.ts',
  modules: true,
  compatibilityDate: '2026-01-01',
  bindings: {
    ANALYTICS: binding,
  },
});

it('writes analytics event on purchase', async () => {
  dataset.clear();
  await mf.dispatchFetch('http://localhost/purchase', {
    method: 'POST',
    body: JSON.stringify({ itemId: 'item-1', price: 9.99 }),
    headers: { 'Content-Type': 'application/json' },
  });

  const events = dataset.getEvents();
  expect(events).toHaveLength(1);
  expect(events[0].doubles).toContain(9.99);
});
```

---

## Using with `@cloudflare/vitest-pool-workers`

The Cloudflare Vitest pool runs tests inside `workerd` (the real runtime), not Node.js. Custom bindings are injected via the `cloudflareTest` setup:

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
        miniflare: {
          // Inject custom bindings into the real workerd runtime
          bindings: {
            ENVIRONMENT: 'test',
          },
          // Service binding mocks must be Workers too in pool-workers mode
          serviceBindings: {
            AUTH_SERVICE: async (request: Request) => {
              // This runs inside workerd — no Node.js APIs
              const token = request.headers.get('Authorization');
              if (token === 'Bearer valid') {
                return Response.json({ userId: '123', valid: true });
              }
              return Response.json({ valid: false }, { status: 401 });
            },
          },
        },
      },
    },
  },
});
```

```typescript
// test/worker.spec.ts
import { env, createExecutionContext, waitOnExecutionContext } from 'cloudflare:test';
import { describe, it, expect } from 'vitest';
import worker from '../src/index';

describe('authenticated route', () => {
  it('rejects requests without a valid token', async () => {
    const ctx = createExecutionContext();
    const response = await worker.fetch(
      new Request('http://localhost/protected'),
      env,
      ctx
    );
    await waitOnExecutionContext(ctx);
    expect(response.status).toBe(401);
  });
});
```

---

## Simulating Binding Errors

Test your Worker's error-handling paths by injecting bindings that throw:

```typescript
// Simulate a D1 database being unavailable
const failingDb = {
  prepare: () => {
    throw new Error('D1_ERROR: Too many connections');
  },
  batch: async () => {
    throw new Error('D1_ERROR: Too many connections');
  },
  exec: async () => {
    throw new Error('D1_ERROR: Too many connections');
  },
  dump: async () => new ArrayBuffer(0),
};

const mf = new Miniflare({
  scriptPath: 'src/index.ts',
  modules: true,
  compatibilityDate: '2026-01-01',
  bindings: {
    DB: failingDb,
  },
});

it('returns 503 when DB is unavailable', async () => {
  const response = await mf.dispatchFetch('http://localhost/users');
  expect(response.status).toBe(503);
  const body = await response.json();
  expect(body.message).toContain('Service temporarily unavailable');
});
```

---

## Anti-Patterns

**Sharing a single `Miniflare` instance across all tests without resetting state.** One test's writes to mock bindings pollute the next test. Use `beforeEach` to clear mock state or `beforeAll`/`afterAll` with a fresh Miniflare instance per test suite.

**Returning `undefined` from mock binding methods.** Cloudflare bindings return typed values; returning `undefined` where a method should return a `Promise<void>` (e.g., `Queue.send()`) causes confusing errors. Always return the correct type from mock methods.

**Mocking only the happy path.** Production binding calls can fail with quota errors, network timeouts, or malformed data. Write at least one test per binding that exercises the error path.

**Using `eval` or `Function` constructor in mock implementations.** `workerd` disables dynamic code evaluation. Mock implementations must use standard functions and closures.

**Not calling `mf.dispose()` after tests.** Miniflare opens `workerd` child processes. Forgetting to dispose causes lingering processes that can conflict with subsequent test runs.

---

## Gotchas

- **Miniflare's `bindings` option accepts JavaScript objects, not serialized JSON.** You can inject class instances, functions, and closures. This is more powerful than what production Workers receive, so don't rely on non-serializable mock behavior to test serialization paths.

- **`serviceBindings` in `@cloudflare/vitest-pool-workers` must be async functions returning `Response`**, not plain objects implementing `Fetcher`. The pool-workers runner wraps these in a lightweight in-process Worker.

- **Miniflare 3 requires Node.js 18+.** It uses `workerd` under the hood, which relies on modern Node.js features. Check CI runner Node.js versions.

- **Custom objects injected as bindings bypass Workers' structured-clone serialization.** In production, data passed between Workers via Service Bindings is serialized. Injecting a mock object directly can hide serialization issues. Use `JSON.parse(JSON.stringify(data))` in mock implementations to catch them.

- **Miniflare's programmatic API is not stable across minor versions.** The `Plugin` interface in particular changes between Miniflare 3.x releases. Pin your Miniflare version precisely in `package.json` and audit the changelog before upgrading.

---

## Verification

```bash
# 1. Run tests with custom bindings
pnpm vitest run

# 2. Confirm mock bindings were called
# (Use console.log in mock methods during debugging)

# 3. Verify Miniflare disposes correctly (no lingering processes)
pnpm vitest run && ps aux | grep workerd
# Expected: no workerd processes after tests finish

# 4. Test error-handling paths
pnpm vitest run --reporter=verbose 2>&1 | grep "503\|unavailable"
# Expected: at least one test verifying the error path
```

```typescript
// Quick integration check: confirm a custom binding is injected and callable
import { Miniflare } from 'miniflare';

const mf = new Miniflare({
  script: `
    export default {
      async fetch(request, env) {
        const value = await env.CUSTOM.getValue();
        return new Response(value);
      }
    }
  `,
  modules: true,
  compatibilityDate: '2026-01-01',
  bindings: {
    CUSTOM: {
      getValue: async () => 'hello from mock',
    },
  },
});

const response = await mf.dispatchFetch('http://localhost/');
console.log(await response.text()); // "hello from mock"
await mf.dispose();
```

---

## Related

- `vitest-workers-miniflare-testing-setup.md` — Full Vitest setup with Miniflare
- `durable-objects-local-debugging.md` — Debugging Durable Objects locally
- `wrangler-dev-remote-d1-r2-bindings.md` — When mocks aren't enough: using remote bindings
- `workers-hmr-live-reload.md` — Fast iteration during Worker development
- `local-https-dev-proxy-wrangler.md` — HTTPS in local Miniflare dev

---

## Sources

- Miniflare documentation: https://miniflare.dev/
- Miniflare programmatic API: https://miniflare.dev/get-started/programmatic
- `@cloudflare/vitest-pool-workers`: https://developers.cloudflare.com/workers/testing/vitest-integration/
- Cloudflare Workers testing guide: https://developers.cloudflare.com/workers/testing/
- `workerd` open-source runtime: https://github.com/cloudflare/workerd
- Service Bindings local testing: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
