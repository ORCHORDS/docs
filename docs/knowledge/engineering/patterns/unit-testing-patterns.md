# unit-testing-patterns

**Issue:** Unit tests for CF Workers — Vitest, mocks, factories
**Date:** 2026-08-09
**Status:** documented

## Symptom
You write tests. They take 30 seconds each. They depend on
D1, R2, KV, the vendor API. CI takes 20 minutes. You skip
the tests on local. You merge broken code. Production
breaks.

## Root cause
**Integration tests are slow.** Setting up D1 + R2 + KV +
vendor API for every test is expensive.

**Source:** Vitest:
https://vitest.dev/

> "Vitest is a blazing-fast unit test framework powered by
> Vite."

## The "test pyramid"

```
       /\
      /  \    E2E tests (Playwright)
     /----\   - Slow (10s per test)
    /      \  - Few (10-20)
   /--------\ Integration tests
  /          \ - Medium (1s per test)
 /------------\ - Some (100s)
/              \ Unit tests
---------------- - Fast (1ms per test)
                - Many (1000s)
```

Most tests should be **unit** (fast, focused). Integration
tests for the glue. E2E for the critical paths.

## The "Vitest" pattern

```ts
// vitest.config.ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    coverage: {
      provider: 'v8',
      include: ['src/**/*.ts'],
      exclude: ['**/*.test.ts', '**/*.d.ts'],
    },
  },
});
```

```ts
// user.test.ts
import { describe, it, expect } from 'vitest';
import { getUser } from './user';

describe('getUser', () => {
  it('returns the user', async () => {
    const result = await getUser('u_123', { env: mockEnv, user: { id: 'u_123' } });
    expect(result).toEqual({ id: 'u_123', email: 'a@x.test' });
  });

  it('returns null for missing user', async () => {
    const result = await getUser('u_missing', { env: mockEnv });
    expect(result).toBeNull();
  });
});
```

## The "mock factory" pattern

```ts
// test/factories.ts
import { vi } from 'vitest';

export function createMockD1(rows: any[] = []): D1Database {
  return {
    prepare: vi.fn().mockReturnValue({
      bind: vi.fn().mockReturnValue({
        first: vi.fn().mockResolvedValue(rows[0] ?? null),
        all: vi.fn().mockResolvedValue({ results: rows }),
        run: vi.fn().mockResolvedValue({ success: true, meta: { last_row_id: 'r_1' } }),
      }),
    }),
  } as any;
}

export function createMockKV(): KVNamespace {
  const store = new Map<string, any>();
  return {
    get: vi.fn((key: string) => Promise.resolve(store.get(key))),
    put: vi.fn((key: string, value: any) => { store.set(key, value); return Promise.resolve(); }),
    delete: vi.fn((key: string) => { store.delete(key); return Promise.resolve(); }),
  } as any;
}

export function createMockR2(): R2Bucket {
  const store = new Map<string, any>();
  return {
    get: vi.fn((key: string) => Promise.resolve(store.get(key) ?? null)),
    put: vi.fn((key: string, value: any) => { store.set(key, value); return Promise.resolve({} as any); }),
    delete: vi.fn((key: string) => { store.delete(key); return Promise.resolve(); }),
    list: vi.fn(() => Promise.resolve({ objects: [], truncated: false })),
  } as any;
}
```

## The "given-when-then" pattern

```ts
describe('createUser', () => {
  it('creates a user with valid input', async () => {
    // Given
    const input = { email: 'a@x.test', displayName: 'Alice' };
    const env = { DB: createMockD1() } as Env;

    // When
    const result = await createUser(input, env);

    // Then
    expect(result.id).toMatch(/^u_/);
    expect(env.DB.prepare).toHaveBeenCalledWith(expect.stringContaining('INSERT INTO users'));
  });
});
```

## The "fixture" pattern

```ts
// test/fixtures.ts
export const testUsers: User[] = [
  { id: 'u_1', email: 'alice@x.test', displayName: 'Alice' },
  { id: 'u_2', email: 'bob@x.test', displayName: 'Bob' },
];

export const testEnv: Env = {
  DB: createMockD1(testUsers),
  KV: createMockKV(),
  R2: createMockR2(),
  // ...
};
```

## The "spy" pattern

```ts
test('login creates a session', async () => {
  const createSessionSpy = vi.spyOn(session, 'createSession');

  await login('a@x.test', 'password', testEnv);

  expect(createSessionSpy).toHaveBeenCalledWith('u_1', testEnv);
});
```

## The "test the edge cases" pattern

```ts
describe('divide', () => {
  it('divides positive numbers', () => {
    expect(divide(10, 2)).toBe(5);
  });

  it('divides negative numbers', () => {
    expect(divide(-10, 2)).toBe(-5);
  });

  it('throws on division by zero', () => {
    expect(() => divide(10, 0)).toThrow('Division by zero');
  });

  it('handles large numbers', () => {
    expect(divide(Number.MAX_SAFE_INTEGER, 2)).toBe(Number.MAX_SAFE_INTEGER / 2);
  });

  it('handles very small numbers', () => {
    expect(divide(0.0001, 0.0001)).toBe(1);
  });
});
```

## The "table-driven test" pattern

```ts
describe('hasFeature', () => {
  const cases = [
    { plan: 'free', feature: 'export', expected: false },
    { plan: 'pro', feature: 'export', expected: true },
    { plan: 'enterprise', feature: 'export', expected: true },
    { plan: 'free', feature: 'basic', expected: true },
  ];

  for (const { plan, feature, expected } of cases) {
    it(`${plan} has ${feature} = ${expected}`, () => {
      expect(hasFeature({ plan } as User, feature as any)).toBe(expected);
    });
  }
});
```

## The "snapshot test" pattern

```ts
it('renders the user card', () => {
  const result = render(<UserCard user={testUser} />);
  expect(result).toMatchSnapshot();
});
```

Update snapshots with:
```bash
vitest --update
```

⚠️ Don't snapshot test dynamic data (timestamps, IDs).

## The "mock the vendor API" pattern

For tests that call a vendor (Stripe, OpenAI), use MSW or a
manual mock:
```ts
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';

const server = setupServer(
  http.post('https://api.openai.com/v1/chat/completions', () => {
    return HttpResponse.json({
      choices: [{ message: { content: 'Hello!' } }],
    });
  }),
);

beforeAll(() => server.listen());
afterAll(() => server.close());
```

## The "CF Workers specific" test pattern

Use `@cloudflare/vitest-pool-workers` to run tests in a
Workers environment:
```ts
// vitest.config.ts
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
      },
    },
  },
});
```

```ts
import { env } from 'cloudflare:test';

test('queries D1', async () => {
  const result = await env.DB.prepare(`SELECT 1 AS x`).first();
  expect(result.x).toBe(1);
});
```

This is the closest you can get to a real Workers environment
in tests.

## The "coverage" targets

| Code | Coverage |
|---|---|
| Critical business logic | 90%+ |
| Utilities | 80%+ |
| Glue code | 60%+ |
| UI / presentation | 50%+ |

100% coverage is a goal, not a requirement. Coverage of
the right code (the bug-prone code) matters more.

## Verification
- **Test:** Tests pass in CI
- **Live:** Coverage is tracked; alerts on regression
- **Audit:** Annual review of test patterns

## Gotchas
- **Test what matters.** Testing trivial getters is a waste
  of time. Test the logic, the boundaries, the edge cases.
- **Mocks are not reality.** A mock that returns the wrong
  shape passes tests but fails in production. Use realistic
  mocks.
- **Flaky tests are worse than no tests.** A test that
  sometimes fails is a test that gets ignored. Fix flaky
  tests immediately.
- **Test the error paths.** A function that handles errors
  correctly is more important than one that handles the
  happy path.
- **The "unit test everything" anti-pattern.** Some code is
  best tested as integration (e.g. a SQL query). Don't
  mock the DB to test a query; test the query.
- **The test name should describe the behavior, not the
  function.** "creates a user" is better than "createUser
  test."

## Related
- `test-pyramid.md`
- `integration-testing-cf.md` (later)
- `e2e-testing-patterns.md` (later)
- `dependency-injection.md` (mockable dependencies)
- `visual-regression-testing.md`
- Vitest: https://vitest.dev/
- CF Workers testing: https://developers.cloudflare.com/workers/testing/
