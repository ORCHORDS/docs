# feature-cookbook-testing

**Issue:** Testing recipes — unit, integration, E2E, mock
**Date:** 2026-08-09
**Status:** documented

## Symptom
You write tests. They take 30 seconds each. They depend
on real DB, real vendor APIs, real time. They fail
randomly. You skip the tests. You ship broken code. You
wish you had a faster, more reliable test setup.

## Root cause
**Tests need to be fast, reliable, and isolated.**

**Source:** Various testing guides.

## The "unit test" pattern

For a pure function:
```ts
import { describe, it, expect } from 'vitest';
import { formatPrice } from './format';

describe('formatPrice', () => {
  it('formats USD', () => {
    expect(formatPrice(99.99, 'USD', 'en-US')).toBe('$99.99');
  });

  it('formats EUR with locale', () => {
    expect(formatPrice(99.99, 'EUR', 'de-DE')).toBe('99,99 €');
  });

  it('handles zero', () => {
    expect(formatPrice(0, 'USD', 'en-US')).toBe('$0.00');
  });

  it('handles negative', () => {
    expect(formatPrice(-10, 'USD', 'en-US')).toBe('-$10.00');
  });
});
```

The test is fast (< 1ms); no setup needed.

## The "mock" pattern

For a function that calls a vendor:
```ts
import { vi } from 'vitest';
import { sendEmail } from './email';

vi.mock('./email');

test('signup sends welcome email', async () => {
  await signup({ email: 'a@x.test' });
  expect(sendEmail).toHaveBeenCalledWith(expect.objectContaining({
    to: 'a@x.test',
    subject: 'Welcome',
  }));
});
```

The mock replaces the real implementation.

## The "DI" pattern for testability

```ts
class UserService {
  constructor(private db: D1Database) {}

  async getById(id: string): Promise<User | null> {
    return this.db.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();
  }
}

// Test
const mockDb = { prepare: vi.fn().mockReturnValue({ bind: vi.fn().mockReturnValue({ first: vi.fn().mockResolvedValue(mockUser) }) }) };
const service = new UserService(mockDb as any);
const user = await service.getById('u_123');
expect(user).toEqual(mockUser);
```

The service is testable because of DI.

## The "integration test" pattern

For a Worker with D1:
```ts
import { env } from 'cloudflare:test';
import { applyD1Migrations, fetchMock } from '@cloudflare/vitest-pool-workers';

beforeEach(async () => {
  await applyD1Migrations(env.DB, env.TEST_MIGRATIONS);
});

test('createUser inserts into D1', async () => {
  await createUser({ email: 'a@x.test' }, env);

  const user = await env.DB!.prepare(`SELECT * FROM users WHERE email = ?`).bind('a@x.test').first();
  expect(user).toBeTruthy();
});
```

The test runs in a real Workers environment with a real D1.

## The "E2E test" pattern

For the full flow:
```ts
import { test, expect } from '@playwright/test';

test('user can sign up and log in', async ({ page }) => {
  await page.goto('https://staging.example.com/signup');
  await page.fill('[name="email"]', 'e2e@test.com');
  await page.fill('[name="password"]', 'password123!');
  await page.click('button[type="submit"]');

  await expect(page).toHaveURL(/dashboard/);

  // Log out
  await page.click('.user-menu');
  await page.click('text=Log out');

  // Log back in
  await page.goto('https://staging.example.com/login');
  await page.fill('[name="email"]', 'e2e@test.com');
  await page.fill('[name="password"]', 'password123!');
  await page.click('button[type="submit"]');

  await expect(page).toHaveURL(/dashboard/);
});
```

The E2E test runs the full flow in a browser.

## The "fixture" pattern

For shared test data:
```ts
// test/fixtures.ts
export const testUsers = {
  alice: { id: 'u_alice', email: 'alice@test.com', displayName: 'Alice', role: 'user' },
  bob: { id: 'u_bob', email: 'bob@test.com', displayName: 'Bob', role: 'user' },
  admin: { id: 'u_admin', email: 'admin@test.com', displayName: 'Admin', role: 'admin' },
};
```

Use fixtures across tests for consistency.

## The "factory" pattern

For dynamic test data:
```ts
import { faker } from '@faker-js/faker';

let counter = 0;

export function makeUser(overrides: Partial<User> = {}): User {
  counter++;
  return {
    id: `u_test_${counter}`,
    email: faker.internet.email(),
    displayName: faker.person.fullName(),
    role: 'user',
    createdAt: new Date().toISOString(),
    ...overrides,
  };
}
```

Each call returns a unique user.

## The "test isolation" pattern

For test isolation, reset the DB before each test:
```ts
beforeEach(async () => {
  await env.DB!.exec(`DELETE FROM users`);
  await env.DB!.exec(`DELETE FROM posts`);
});
```

Each test starts with a clean DB.

## The "snapshot" pattern

For UI tests:
```ts
test('renders the user card', () => {
  const { container } = render(<UserCard user={testUser} />);
  expect(container).toMatchSnapshot();
});
```

Update snapshots: `vitest --update`.

## The "spy" pattern

For verifying a function was called:
```ts
import { vi } from 'vitest';
import { sendEmail } from './email';

const sendEmailSpy = vi.spyOn(await import('./email'), 'sendEmail');

test('signup sends email', async () => {
  await signup({ email: 'a@x.test' });
  expect(sendEmailSpy).toHaveBeenCalledOnce();
});
```

The spy monitors the function.

## The "test coverage" pattern

For coverage:
```ts
// vitest.config.ts
export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      include: ['src/**/*.ts'],
      exclude: ['**/*.test.ts', '**/*.spec.ts'],
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 70,
      },
    },
  },
});
```

Coverage is enforced.

## The "test the unhappy path" pattern

For error cases:
```ts
test('getUser returns null for missing user', async () => {
  const result = await userService.getById('u_missing');
  expect(result).toBeNull();
});

test('getUser throws on DB error', async () => {
  vi.mocked(env.DB!.prepare).mockImplementation(() => { throw new Error('DB down'); });
  await expect(userService.getById('u_123')).rejects.toThrow('DB down');
});

test('getUser returns null for soft-deleted user', async () => {
  await env.DB!.exec(`INSERT INTO users (id, email, deleted_at) VALUES ('u_123', 'a@x.test', '${new Date().toISOString()}')`);
  const result = await userService.getById('u_123');
  expect(result).toBeNull();
});
```

Test the error paths.

## The "test performance" pattern

For slow tests, profile:
```ts
test('large query is fast', async () => {
  // Seed 10k users
  await seedUsers(10_000, env);

  const start = Date.now();
  const result = await userService.list({ limit: 100 }, env);
  const duration = Date.now() - start;

  expect(result.length).toBe(100);
  expect(duration).toBeLessThan(100);  // p99 < 100ms
});
```

The test asserts the performance.

## The "test description" pattern

For readable test names:
```ts
describe('UserService', () => {
  describe('getById', () => {
    it('returns the user when found', ...);
    it('returns null when not found', ...);
    it('throws on database error', ...);
    it('excludes soft-deleted users', ...);
  });
});
```

The describe + it tree describes the behavior.

## The "test the boundary" pattern

For boundary conditions:
```ts
test('handles empty list', ...);
test('handles single item', ...);
test('handles many items', ...);
test('handles null', ...);
test('handles undefined', ...);
test('handles very large numbers', ...);
test('handles special characters', ...);
```

The boundaries are tested.

## Verification
- **Test:** Tests pass
- **Test:** Coverage meets the threshold
- **Live:** CI runs the tests
- **Audit:** Quarterly review of test patterns

## Gotchas
- **The "test depends on time" anti-pattern.** Mock the
  time; don't depend on `Date.now()`.
- **The "test depends on network" anti-pattern.** Mock
  the network; don't make real calls.
- **The "test depends on the order" anti-pattern.** Tests
  should be independent; reset state between.
- **The "test with real production data" anti-pattern.**
  Use fake data; never use real customer data.
- **The "test that always passes" anti-pattern.** A test
  that always passes is a false sense of safety. Make it
  fail.

## Related
- `test-pyramid.md`
- `unit-testing-patterns.md`
- `integration-testing-cf.md` (later)
- `e2e-testing-patterns.md`
- `test-data-management.md`
- `dependency-injection.md`
- Vitest: https://vitest.dev/
- Playwright: https://playwright.dev/
- CF testing: https://developers.cloudflare.com/workers/testing/
