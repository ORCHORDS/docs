# feature-cookbook-testing-strategies

**Issue:** Testing strategies — pyramid, types, mocking
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have 100 unit tests + 0 integration tests + 0 E2E
tests. The unit tests pass. The integration breaks. You
ship a bug. The user complains.

## Root cause
**Unit tests alone don't cover the integration.** Use
the test pyramid.

**Source:** Martin Fowler — Test Pyramid:
https://martinfowler.com/bliki/TestPyramid.html

## The "test pyramid" concept

For a healthy test suite:
```
        /\
       /  \     E2E (few, slow, high value)
      /----\
     /      \   Integration (some, medium)
    /--------\
   /          \  Unit (many, fast, low value)
  /------------\
```

- **Unit:** Many, fast, isolated
- **Integration:** Some, medium, with deps
- **E2E:** Few, slow, full flow

The pyramid has a wide base of unit tests.

## The "unit test" pattern

For a unit test:
```ts
import { describe, test, expect } from 'vitest';

describe('add', () => {
  test('adds two positive numbers', () => {
    expect(add(2, 3)).toBe(5);
  });

  test('adds negative numbers', () => {
    expect(add(-2, -3)).toBe(-5);
  });
});
```

The unit test is fast + isolated.

## The "integration test" pattern

For an integration test:
```ts
import { describe, test, expect } from 'vitest';

describe('POST /api/users', () => {
  test('creates a user', async () => {
    const response = await fetch('http://localhost:8787/api/users', {
      method: 'POST',
      body: JSON.stringify({ email: 'alice@example.com' }),
    });

    expect(response.status).toBe(201);
    const user = await response.json();
    expect(user.email).toBe('alice@example.com');
  });
});
```

The integration test uses the real DB + Worker.

## The "E2E test" pattern

For an E2E test:
```ts
import { test, expect } from '@playwright/test';

test('user can sign up and post', async ({ page }) => {
  await page.goto('https://example.com/signup');
  await page.fill('input[name="email"]', 'alice@example.com');
  await page.fill('input[name="password"]', 'password123');
  await page.click('button[type="submit"]');

  await expect(page).toHaveURL('https://example.com/dashboard');
  await expect(page.locator('h1')).toContainText('Welcome');
});
```

The E2E test uses a real browser.

## The "mock" pattern

For mocks, isolate the unit:
```ts
import { vi } from 'vitest';

const db = {
  prepare: vi.fn().mockReturnValue({
    bind: vi.fn().mockReturnValue({
      first: vi.fn().mockResolvedValue({ id: 'u_1', email: 'alice@example.com' }),
    }),
  }),
};

const env = { DB: db } as unknown as Env;

const user = await getUser('u_1', env);
expect(user.email).toBe('alice@example.com');
```

The mock is fast + predictable.

## The "fixture" pattern

For fixtures, reuse test data:
```ts
export const userFixture = {
  id: 'u_1',
  email: 'alice@example.com',
  displayName: 'Alice',
};

export const postFixture = {
  id: 'p_1',
  authorId: 'u_1',
  title: 'Test post',
};

export function seedTestData(db: D1Database) {
  await db.prepare(`INSERT INTO users ...`).bind(userFixture.id, userFixture.email).run();
  await db.prepare(`INSERT INTO posts ...`).bind(postFixture.id, postFixture.authorId).run();
}
```

The fixture is reusable.

## The "test database" pattern

For a test DB, use a separate database:
```ts
const TEST_DB = ':memory:';  // SQLite in-memory

// Or, a separate D1 for tests
const env = { DB: testDbInstance };
```

The test DB is isolated.

## The "snapshot" pattern

For snapshots, compare the output:
```ts
test('renders correctly', () => {
  const html = render(<UserCard user={userFixture} />);
  expect(html).toMatchSnapshot();
});
```

The snapshot is a record of the output.

## The "contract test" pattern

For contract tests, verify the API:
```ts
// Consumer side
test('GET /users/123 matches contract', async () => {
  const response = await fetch('https://api.example.com/users/123');
  const user = await response.json();

  expect(user).toMatchSchema(userSchema);
});

// Provider side
test('GET /users/123 returns User schema', async () => {
  const response = await getUser('123', env);
  expect(response).toMatchSchema(userSchema);
});
```

The contract is enforced.

## The "test coverage" pattern

For coverage, set a target:
```bash
# vitest
npx vitest --coverage
```

Target: **80% coverage** (the Pareto).

Don't chase 100%; focus on the critical paths.

## The "test naming" pattern

For naming:
- **describe:** The function/feature
- **it/test:** The behavior
- **Pattern:** "should do X when Y"

```ts
describe('add', () => {
  it('should return the sum of two positive numbers', () => {
    expect(add(2, 3)).toBe(5);
  });

  it('should return 0 when given 0 and 0', () => {
    expect(add(0, 0)).toBe(0);
  });
});
```

The name describes the behavior.

## The "test anti-pattern" anti-patterns

### 1. No tests
- **Issue:** Bugs ship
- **Fix:** Test the critical paths

### 2. Tests that don't fail
- **Issue:** Tests pass on a broken implementation
- **Fix:** Test the behavior, not the implementation

### 3. Brittle tests
- **Issue:** Every change breaks the test
- **Fix:** Test the public API, not the internals

### 4. Slow tests
- **Issue:** Nobody runs them
- **Fix:** Unit tests for the bulk; integration for the
  important

### 5. Mocking the unit under test
- **Issue:** The test doesn't test the unit
- **Fix:** Mock dependencies, not the unit

### 6. No fixtures
- **Issue:** Copy-paste everywhere
- **Fix:** Central fixtures

### 7. No coverage target
- **Issue:** Coverage drifts
- **Fix:** Set 80% target

## The "test in CI" pattern

For tests in CI:
```yaml
- name: Test
  run: |
    npm run lint
    npm run typecheck
    npm test
    npm run build
```

The CI runs all tests on every PR.

## The "test before code" pattern

For TDD:
1. **Write the test:** What should it do?
2. **Run it:** Fails (no implementation)
3. **Write the code:** Make it pass
4. **Run it:** Passes
5. **Refactor:** Clean up

TDD is a discipline.

## Verification
- **Test:** All tests pass
- **Test:** Coverage > 80%
- **Test:** CI is green
- **Live:** Test suite is fast (< 5 min)
- **Audit:** Quarterly test review

## Gotchas
- **The "no tests" anti-pattern.** Test the critical
  paths.
- **The "brittle tests" anti-pattern.** Test the public
  API.
- **The "mocking the unit under test" anti-pattern.**
  Mock dependencies.
- **The "no coverage target" anti-pattern.** Set a
  target.

## Related
- `test-pyramid.md`
- `test-data-management.md`
- `contract-testing.md`
- `visual-regression-testing.md`
- `load-testing.md`
- `feature-cookbook-testing.md`
- `feature-cookbook-testing-frontend.md`
- Vitest: https://vitest.dev/
- Playwright: https://playwright.dev/
- Martin Fowler: https://martinfowler.com/bliki/TestPyramid.html
