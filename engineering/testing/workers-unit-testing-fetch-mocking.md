# workers-unit-testing-fetch-mocking

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

Unit tests for a Cloudflare Worker throw
`TypeError: fetch is not defined`, or silently call the
real network, or crash because `env.DB` / `env.MY_KV` /
`env.MY_BUCKET` are undefined. Tests that do pass work
only on a developer laptop where `wrangler dev` happens to
be running and real bindings are injected.

## Context

A Cloudflare Worker's entry point receives a `Request` and
an `Env` object populated by the Cloudflare runtime. In a
Node.js or Vitest unit-test context neither the global
`fetch` nor the binding values exist unless you provide
them. The idiomatic approach is to use
`@cloudflare/vitest-pool-workers` for realistic integration
tests (see `miniflare-d1-integration-testing.md`) or to
hand-craft lightweight fakes for the bindings and intercept
`fetch` at the module level for pure unit tests that run in
under 100 ms. This article covers the lightweight-fake
approach.

## Mocking the Global fetch

`@cloudflare/vitest-pool-workers` exposes `fetchMock` for
intercepting outbound fetch from inside `workerd`. For
plain Vitest (Node pool), use `vi.stubGlobal`:

```ts
// tests/setup.ts  (referenced from vitest.config.ts setupFiles)
import { vi } from 'vitest';

// Provide a typed stub; replace per-test as needed
vi.stubGlobal('fetch', vi.fn());
```

Per-test override:

```ts
import { vi, it, expect, beforeEach } from 'vitest';
import { handleRequest } from '../src/worker';

beforeEach(() => {
  vi.mocked(fetch).mockReset();
});

it('proxies upstream and returns JSON', async () => {
  vi.mocked(fetch).mockResolvedValueOnce(
    new Response(JSON.stringify({ data: 42 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  );

  const req = new Request('https://example.com/api/items');
  const res = await handleRequest(req, fakeEnv);

  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining('/upstream/items'),
    expect.any(Object)
  );
  expect(res.status).toBe(200);
});
```

## D1 Mock Pattern

Minimal D1 fake that satisfies TypeScript's `D1Database`
interface for the methods your Worker uses:

```ts
// tests/fakes/d1.ts
import { vi } from 'vitest';

function makeStatement(rows: unknown[] = []) {
  const stmt = {
    bind:  (..._args: unknown[]) => stmt,
    first: vi.fn().mockResolvedValue(rows[0] ?? null),
    all:   vi.fn().mockResolvedValue({
      results: rows,
      success: true,
      meta: {},
    }),
    run:   vi.fn().mockResolvedValue({
      success: true,
      meta: { changes: 1, last_row_id: 1 },
    }),
  };
  return stmt;
}

export function makeD1Mock(
  rows: Record<string, unknown[]> = {}
) {
  return {
    prepare: vi.fn((sql: string) =>
      makeStatement(rows[sql] ?? [])
    ),
    exec: vi.fn().mockResolvedValue({ count: 0, duration: 0 }),
    batch: vi.fn().mockResolvedValue([]),
    dump:  vi.fn().mockResolvedValue(new ArrayBuffer(0)),
  } satisfies Partial<D1Database>;
}
```

Usage:

```ts
import { makeD1Mock } from './fakes/d1';

it('fetches a user by id', async () => {
  const mockUser = { id: 'u1', name: 'Alice', role: 'admin' };
  const db = makeD1Mock({
    'SELECT * FROM users WHERE id = ?': [mockUser],
  });

  const env = { DB: db } as unknown as Env;
  const req = new Request('https://app.example/api/users/u1');
  const res = await handleRequest(req, env);

  expect(db.prepare).toHaveBeenCalledWith(
    'SELECT * FROM users WHERE id = ?'
  );
  const body = await res.json<typeof mockUser>();
  expect(body.name).toBe('Alice');
});
```

## KV Mock Pattern

```ts
// tests/fakes/kv.ts
import { vi } from 'vitest';

export function makeKVMock(
  store: Record<string, string> = {}
) {
  const data = new Map<string, string>(Object.entries(store));

  return {
    get: vi.fn(async (key: string) => data.get(key) ?? null),
    put: vi.fn(async (key: string, value: string) => {
      data.set(key, value);
    }),
    delete: vi.fn(async (key: string) => {
      data.delete(key);
    }),
    list: vi.fn(async () => ({
      keys: [...data.keys()].map((name) => ({ name })),
      list_complete: true,
      cursor: '',
    })),
    getWithMetadata: vi.fn(async (key: string) => ({
      value: data.get(key) ?? null,
      metadata: null,
    })),
  } satisfies Partial<KVNamespace>;
}
```

```ts
it('caches API response in KV', async () => {
  const kv  = makeKVMock({});
  const env = { CACHE: kv } as unknown as Env;

  vi.mocked(fetch).mockResolvedValueOnce(
    new Response('{"result":"ok"}', { status: 200 })
  );

  await handleRequest(
    new Request('https://app.example/api/data'),
    env
  );

  expect(kv.put).toHaveBeenCalledWith(
    '/api/data',
    expect.any(String)
  );
});
```

## R2 Mock Pattern

```ts
// tests/fakes/r2.ts
import { vi } from 'vitest';

export function makeR2Mock(
  objects: Record<string, Uint8Array> = {}
) {
  const store = new Map(
    Object.entries(objects).map(([k, v]) => [k, v])
  );

  const makeObject = (key: string, body: Uint8Array) => ({
    key,
    arrayBuffer: async () => body.buffer,
    text:        async () => new TextDecoder().decode(body),
    json:        async () => JSON.parse(
      new TextDecoder().decode(body)
    ),
    body:        null,
    bodyUsed:    false,
    size:        body.byteLength,
    etag:        '"mock-etag"',
    httpEtag:    '"mock-etag"',
    checksums:   {},
    uploaded:    new Date(),
    httpMetadata: {},
    customMetadata: {},
    writeHttpMetadata: vi.fn(),
  });

  return {
    get: vi.fn(async (key: string) => {
      const val = store.get(key);
      return val ? makeObject(key, val) : null;
    }),
    put: vi.fn(
      async (key: string, value: ArrayBuffer | string) => {
        const bytes =
          typeof value === 'string'
            ? new TextEncoder().encode(value)
            : new Uint8Array(value);
        store.set(key, bytes);
        return makeObject(key, bytes);
      }
    ),
    delete: vi.fn(async (key: string) => {
      store.delete(key);
    }),
    head: vi.fn(async (key: string) => {
      const val = store.get(key);
      return val ? makeObject(key, val) : null;
    }),
    list: vi.fn(async () => ({
      objects: [...store.keys()].map((key) =>
        makeObject(key, store.get(key)!)
      ),
      truncated: false,
      delimitedPrefixes: [],
    })),
  } satisfies Partial<R2Bucket>;
}
```

## Mobile User-Agent Request Simulation

Simulate mobile and desktop callers without a browser:

```ts
// tests/helpers/requests.ts
export const UA = {
  mobileIOS:
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) ' +
    'AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1',
  mobileAndroid:
    'Mozilla/5.0 (Linux; Android 14; Pixel 8) ' +
    'AppleWebKit/537.36 Mobile Safari/537.36',
  desktop:
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ' +
    'AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36',
} as const;

export function mobileRequest(path: string): Request {
  return new Request(`https://example project.example${path}`, {
    headers: {
      'User-Agent':     UA.mobileIOS,
      'CF-Device-Type': 'mobile',
      'Accept':         'application/json',
    },
  });
}

export function desktopRequest(path: string): Request {
  return new Request(`https://example project.example${path}`, {
    headers: {
      'User-Agent':     UA.desktop,
      'CF-Device-Type': 'desktop',
      'Accept':         'text/html,application/json;q=0.9',
    },
  });
}
```

```ts
it('returns condensed payload for mobile', async () => {
  const env = buildEnv();
  const res = await handleRequest(
    mobileRequest('/api/events'),
    env
  );
  const body = await res.json<{ items: unknown[] }>();
  // Mobile response omits heavy description fields
  expect(body.items[0]).not.toHaveProperty('description');
});
```

Binding mock comparison:

| Binding | Key fake method(s)          | Reset between tests?    |
|---------|-----------------------------|-------------------------|
| D1      | `prepare`, `batch`, `exec`  | Yes — `vi.fn().mock...` |
| KV      | `get`, `put`, `delete`      | Recreate the Map        |
| R2      | `get`, `put`, `list`        | Recreate the Map        |
| Queue   | `send`, `sendBatch`         | `vi.fn().mockReset()`   |

## Anti-patterns

- Letting `fetch` call the real network in unit tests —
  tests become flaky and slow; CI fails on network errors.
- Building a D1 mock that returns plain objects instead of
  `Promise<…>` — the Worker `await`s the result; a sync
  return causes `TypeError: Cannot read property of
  undefined`.
- Sharing a mutable `Map` across tests inside a KV or R2
  mock — cross-test pollution surfaces as order-dependent
  failures.
- Using `as any` to cast the env object instead of
  `as unknown as Env` — TypeScript's `--strict` flag
  flags `as any` casts; the double-cast documents intent.
- Mocking `fetch` globally without resetting in
  `beforeEach` — a resolved mock from one test bleeds into
  the next.

## Gotchas

- `vi.stubGlobal('fetch', vi.fn())` only works in the Node
  pool. In `@cloudflare/vitest-pool-workers`, use the
  `fetchMock` API exported from `cloudflare:test` — the
  global fetch is not the same object in `workerd`.
- `new Response(body, init)` in Node.js 18+ is the Web
  `Response`, but older Node versions require the polyfill
  from `@miniflare/core` or `undici`. Pin Node >= 18.
- D1 `prepare()` returns a `D1PreparedStatement`, not the
  result. The mock must chain `.bind()` before `.run()` /
  `.first()` / `.all()` — callers that skip `.bind()` will
  hit `.run()` on the stub returned by `prepare`.
- `R2Object.body` is a `ReadableStream` in production, not
  null. If the Worker calls `.body.pipeTo()`, the mock
  needs a real `ReadableStream` or the test will throw.

## Verification

```bash
# Run unit tests only (Node pool, no workerd)
npx vitest run tests/unit/ --reporter=verbose

# Confirm no real network calls were made
# (fetch mock should have been called, not the real fetch)
npx vitest run --reporter=verbose 2>&1 \
  | grep -E 'fetch|network'

# Type-check the fake implementations
npx tsc --noEmit
```

All unit tests should complete in under 5 seconds with no
network access and no `wrangler` process required.

## Related

- `testing/miniflare-d1-integration-testing.md`
- `testing/kv-testing-miniflare.md`
- `testing/test-doubles-cloudflare-workers.md`
- `testing/mock-server-msw.md`
- `testing/workers-test-patterns.md`

## Source URLs (verified 2026-08-22)

- https://developers.cloudflare.com/workers/testing/vitest-integration/get-started/
- https://developers.cloudflare.com/workers/testing/unit-tests/
- https://developers.cloudflare.com/d1/worker-api/
- https://vitest.dev/api/vi#vi-stubglobal
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
