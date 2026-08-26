# Golden File (Snapshot) Testing for Workers API Responses

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Workers API serializes complex objects — nested user records, computed summary fields, formatted dates — and you want to catch unintended changes to the response shape or content without writing brittle field-by-field assertions. A change to a date formatting utility silently alters every API response, and no existing test flags it. Golden file (snapshot) testing captures the exact response once and fails any run where the output has changed, forcing explicit acknowledgment of every serialization change.

---

## Context
Vitest's snapshot testing (`toMatchSnapshot` and `toMatchInlineSnapshot`) works with `SELF.fetch()` responses from the Workers runtime. Snapshots are stored in `__snapshots__` directories alongside test files and must be committed to the repository, making every response change visible in code review. Inline snapshots embed the expected value directly in the test file, which works well for small payloads. For larger responses, external snapshot files keep tests readable. Deterministic test data seeded into D1 with fixed IDs and timestamps is essential — any non-determinism in the response (random IDs, `Date.now()`) will cause every snapshot run to produce a false failure.

---

## D1 Deterministic Fixture Seeding

```typescript
// test/fixtures/seed.ts
import type { D1Database } from '@cloudflare/workers-types';

/**
 * Seeds D1 with deterministic, fixed-value test data.
 * All IDs and timestamps are hardcoded — no randomness, no Date.now().
 */
export async function seedDeterministicData(db: D1Database): Promise<void> {
  // Truncate in dependency order
  await db.batch([
    db.prepare('DELETE FROM posts'),
    db.prepare('DELETE FROM users'),
  ]);

  // Fixed users
  await db.batch([
    db.prepare(
      `INSERT INTO users (id, name, email, role, created_at) VALUES (?, ?, ?, ?, ?)`
    ).bind('u-001', 'Alice Nguyen', 'alice@example.com', 'admin', '2026-01-01T00:00:00.000Z'),
    db.prepare(
      `INSERT INTO users (id, name, email, role, created_at) VALUES (?, ?, ?, ?, ?)`
    ).bind('u-002', 'Bob Smith', 'bob@example.com', 'editor', '2026-01-02T00:00:00.000Z'),
    db.prepare(
      `INSERT INTO users (id, name, email, role, created_at) VALUES (?, ?, ?, ?, ?)`
    ).bind('u-003', 'Carol White', 'carol@example.com', 'viewer', '2026-01-03T00:00:00.000Z'),
  ]);

  // Fixed posts
  await db.batch([
    db.prepare(
      `INSERT INTO posts (id, title, author_id, published_at) VALUES (?, ?, ?, ?)`
    ).bind('p-001', 'First Post', 'u-001', '2026-02-01T12:00:00.000Z'),
    db.prepare(
      `INSERT INTO posts (id, title, author_id, published_at) VALUES (?, ?, ?, ?)`
    ).bind('p-002', 'Second Post', 'u-002', '2026-02-15T08:30:00.000Z'),
  ]);
}
```

---

## Snapshot Tests with SELF.fetch()

```typescript
// test/snapshot/api-responses.snapshot.test.ts
import { env, SELF } from 'cloudflare:test';
import { describe, it, expect, beforeAll } from 'vitest';
import { seedDeterministicData } from '../fixtures/seed';

declare module 'cloudflare:test' {
  interface ProvidedEnv extends Env {}
}

beforeAll(async () => {
  await seedDeterministicData(env.DB);
});

describe('GET /api/users — snapshot', () => {
  it('response body matches snapshot', async () => {
    const res = await SELF.fetch('http://localhost/api/users?sort=created_at&order=asc');
    expect(res.status).toBe(200);
    // toMatchSnapshot() writes to __snapshots__/api-responses.snapshot.test.ts.snap on first run
    expect(await res.json()).toMatchSnapshot();
  });

  it('response headers match snapshot', async () => {
    const res = await SELF.fetch('http://localhost/api/users');
    // Only snapshot headers your API explicitly sets — avoid snapshotting Date or CF-Ray
    const relevant = {
      'content-type': res.headers.get('content-type'),
      'cache-control': res.headers.get('cache-control'),
      'x-total-count': res.headers.get('x-total-count'),
    };
    expect(relevant).toMatchSnapshot();
  });
});

describe('GET /api/users/:id — inline snapshot for small payload', () => {
  it('known user matches inline snapshot', async () => {
    const res = await SELF.fetch('http://localhost/api/users/u-001');
    expect(res.status).toBe(200);
    // toMatchInlineSnapshot() embeds the value directly in the test file on first run
    expect(await res.json()).toMatchInlineSnapshot(`
      {
        "createdAt": "2026-01-01T00:00:00.000Z",
        "email": "alice@example.com",
        "id": "u-001",
        "name": "Alice Nguyen",
        "postCount": 1,
        "role": "admin",
      }
    `);
  });
});

describe('GET /api/posts — snapshot', () => {
  it('post list with embedded author matches snapshot', async () => {
    const res = await SELF.fetch('http://localhost/api/posts?include=author');
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchSnapshot();
  });
});

describe('Error responses — inline snapshots', () => {
  it('404 body matches inline snapshot', async () => {
    const res = await SELF.fetch('http://localhost/api/users/does-not-exist');
    expect(res.status).toBe(404);
    expect(await res.json()).toMatchInlineSnapshot(`
      {
        "code": 404,
        "error": "User not found",
      }
    `);
  });

  it('400 body for missing required fields matches inline snapshot', async () => {
    const res = await SELF.fetch('http://localhost/api/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    expect(res.status).toBe(400);
    expect(await res.json()).toMatchInlineSnapshot(`
      {
        "code": 400,
        "error": "Validation failed: name is required, email is required",
      }
    `);
  });
});
```

---

## Updating Snapshots

```bash
# Update all snapshots (run after an intentional response change)
npx vitest run --update-snapshots

# Update snapshots for a single test file
npx vitest run test/snapshot/api-responses.snapshot.test.ts --update-snapshots

# Interactive mode: review each change before accepting
npx vitest --update-snapshots

# Review the diff of snapshot changes before committing
git diff test/snapshot/__snapshots__/
```

---

## CI Configuration

```yaml
# .github/workflows/snapshot.yml
name: Snapshot Tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  snapshot:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci

      - name: Run snapshot tests
        # --update-snapshots is intentionally NOT passed here.
        # CI must fail when snapshots are stale — snapshots are updated locally.
        run: npx vitest run test/snapshot --reporter=verbose

      - name: Fail if snapshots were modified
        # Extra guard: catches cases where a test somehow auto-updated snapshots
        run: |
          if ! git diff --exit-code test/snapshot/__snapshots__/; then
            echo 'ERROR: Snapshot files were modified during CI. Commit updated snapshots.'
            exit 1
          fi
```

---

## Anti-patterns
- **Snapshotting non-deterministic fields** — Any field that contains a timestamp from `Date.now()`, a randomly generated UUID, or a request ID will cause snapshot failures on every run. Strip or replace these fields before snapshotting, or ensure they are always set from fixed seed data.
- **Using `--update-snapshots` in CI** — Automatically updating snapshots in CI defeats the purpose: the test becomes a no-op that always passes. Snapshots must only be updated locally with explicit developer review of the diff.
- **Snapshotting enormous responses** — A snapshot of a 500-field nested object is unreadable in a diff and defeats the purpose of making changes visible. For large responses, snapshot a representative subset or use contract tests instead.
- **Not committing snapshot files** — Snapshot files in `__snapshots__/` must be committed to version control. If they are gitignored, every CI run regenerates them from scratch and changes are never caught.

---

## Gotchas
- Vitest serializes objects with keys in alphabetical order in snapshots, regardless of insertion order. Your source object key order does not affect the snapshot format.
- `toMatchInlineSnapshot` modifies the test file on disk when you run with `--update-snapshots`. Commit the updated test file, not a separate snapshot file.
- If your D1 schema has a column with a default of `CURRENT_TIMESTAMP`, the value will differ on every test run. Override it explicitly in your seed SQL with a fixed string value.
- The `SELF.fetch()` call must resolve before calling `toMatchSnapshot`. Using `await` on `res.json()` inside the `expect()` call is required — do not snapshot the `Response` object itself.
- Vitest snapshot format differs from Jest's. If migrating from Jest, run `--update-snapshots` once to regenerate all files in Vitest's format.

---

## Verification

```bash
# Run snapshot tests and create snapshots on first run
npx vitest run test/snapshot

# Confirm snapshot files were created
ls test/snapshot/__snapshots__/

# Run again to verify snapshots pass (should produce zero failures)
npx vitest run test/snapshot --reporter=verbose

# Simulate a response change and observe failure
# Edit src/handlers/users.ts to add a field, then:
npx vitest run test/snapshot 2>&1 | grep -A 20 'Snapshot'

# Review what changed
git diff test/snapshot/__snapshots__/
```

---

## Related
- `workers-api-contract-testing-zod.md`
- `workers-property-based-testing-fast-check.md`
- `workers-test-coverage-c8-vitest.md`

---

## Sources
- Vitest snapshot testing — https://vitest.dev/guide/snapshot
- Cloudflare Workers Vitest integration — https://developers.cloudflare.com/workers/testing/vitest-integration/
- Miniflare D1 local simulation — https://miniflare.dev/storage/d1
- Vitest inline snapshots — https://vitest.dev/guide/snapshot#inline-snapshots
