# D1 Test Fixture Seeding with Wrangler and Miniflare

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project integration tests against D1 read stale or missing data because each developer seeds their local database differently. CI runs fail intermittently when tests assume fixture rows inserted by a previous test. The `beforeEach` hook is absent or resets only some tables, leaving foreign-key-dependent tests in a broken state.

## Context

example project stores tracks, users, and playlist data in a Cloudflare D1 SQLite database. Tests need a known fixture state before each test. Two complementary approaches exist: Wrangler `execute` for seeding a real D1 instance (local or remote preview), and Miniflare's in-process D1 for fast unit and integration tests. This article covers both, with a focus on the `beforeEach` reset pattern that guarantees isolation.

Toolchain: Wrangler 3.x, Miniflare 3.x, Vitest 2.x, D1 schema migrations via `wrangler d1 migrations apply`.

## Wrangler Execute for Local D1 Seeding

Create a seed SQL file that is idempotent (DELETE + INSERT):

```sql
-- db/seeds/test-fixtures.sql
DELETE FROM playlist_tracks;
DELETE FROM playlists;
DELETE FROM tracks;
DELETE FROM users;

INSERT INTO users (id, email, tier) VALUES
  (1, 'alice@example.com', 'pro'),
  (2, 'bob@example.com', 'free');

INSERT INTO tracks (id, user_id, title, duration_ms, bpm, genre) VALUES
  (1, 1, 'Morning Groove',   210000, 128, 'electronic'),
  (2, 1, 'Late Night Jazz',  340000,  90, 'jazz'),
  (3, 2, 'Folk Strum',       180000,  75, 'folk');

INSERT INTO playlists (id, user_id, name) VALUES
  (1, 1, 'My Favourites');

INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES
  (1, 1, 0),
  (1, 2, 1);
```

Run against local D1:

```bash
wrangler d1 execute example project-db --local --file=db/seeds/test-fixtures.sql
```

Run against a named preview environment:

```bash
wrangler d1 execute example project-db --env=preview --file=db/seeds/test-fixtures.sql
```

| Flag        | Effect                                                |
|-------------|-------------------------------------------------------|
| `--local`   | Uses `.wrangler/state/v3/d1/` SQLite file             |
| `--env`     | Targets `[env.preview]` binding in `wrangler.toml`    |
| `--file`    | Executes all statements in the SQL file               |
| `--command` | One-off SQL string without a file                     |

## Per-Test Database Isolation with Miniflare

For vitest integration tests, spin up a Miniflare instance with a fresh in-memory D1 per test file:

```typescript
// tests/integration/helpers/miniflare-setup.ts
import { Miniflare } from "miniflare";
import { readFileSync } from "node:fs";
import path from "node:path";

const SCHEMA_SQL  = readFileSync(path.resolve("db/schema.sql"),  "utf8");
const FIXTURE_SQL = readFileSync(path.resolve("db/seeds/test-fixtures.sql"), "utf8");

export async function createTestMiniflare(): Promise<Miniflare> {
  const mf = new Miniflare({
    modules:      true,
    scriptPath:   "./dist/worker.js",
    d1Databases:  ["DB"],
  });
  const db = await mf.getD1Database("DB");
  await db.exec(SCHEMA_SQL);   // create tables
  await db.exec(FIXTURE_SQL);  // insert fixtures
  return mf;
}

export async function resetD1(mf: Miniflare): Promise<void> {
  const db = await mf.getD1Database("DB");
  await db.exec(FIXTURE_SQL);  // idempotent: DELETE + INSERT
}
```

## `beforeEach` Reset Pattern

```typescript
// tests/integration/tracks-api.test.ts
import { Miniflare } from "miniflare";
import { createTestMiniflare, resetD1 } from "./helpers/miniflare-setup";

let mf: Miniflare;

beforeAll(async () => {
  mf = await createTestMiniflare();
});

beforeEach(async () => {
  await resetD1(mf); // restore known state before every test
});

afterAll(async () => {
  await mf.dispose();
});

describe("GET /api/tracks", () => {
  it("returns all 3 fixture tracks", async () => {
    const res = await mf.dispatchFetch("https://api.example.com/api/tracks");
    const body = await res.json<{ items: unknown[]; total: number }>();
    expect(body.total).toBe(3);
    expect(body.items).toHaveLength(3);
  });

  it("filters by genre=jazz and returns 1 result", async () => {
    const res = await mf.dispatchFetch(
      "https://api.example.com/api/tracks?genre=jazz"
    );
    const body = await res.json<{ items: { genre: string }[] }>();
    expect(body.items).toHaveLength(1);
    expect(body.items[0].genre).toBe("jazz");
  });

  it("DELETE /api/tracks/1 leaves 2 tracks for next test", async () => {
    const del = await mf.dispatchFetch(
      "https://api.example.com/api/tracks/1",
      { method: "DELETE" }
    );
    expect(del.status).toBe(204);

    const list = await mf.dispatchFetch("https://api.example.com/api/tracks");
    const body = await list.json<{ total: number }>();
    expect(body.total).toBe(2);
    // beforeEach will reset to 3 tracks for the next test
  });
});
```

## Wrangler Seed in CI

```yaml
# .github/workflows/integration.yml
jobs:
  integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npm run build

      - name: Apply migrations to local D1
        run: |
          wrangler d1 migrations apply example project-db --local
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Seed test fixtures
        run: wrangler d1 execute example project-db --local --file=db/seeds/test-fixtures.sql

      - name: Run integration tests
        run: npx vitest run tests/integration/
```

Note: Wrangler `--local` does not require `CLOUDFLARE_API_TOKEN`; the env var is included for completeness in workflows that also run remote operations.

## Schema and Seed Script Discipline

| Rule                            | Why it matters                                              |
|---------------------------------|-------------------------------------------------------------|
| IDs are explicit integers        | Avoids auto-increment drift across seeds                    |
| FK-dependent tables seeded last  | Prevents constraint violation on INSERT                     |
| Seed script is idempotent        | `DELETE` before `INSERT` — safe to run multiple times       |
| Seed script is version-controlled | Tracks evolve with schema migrations                       |
| Separate seeds per environment   | `test-fixtures.sql` vs `dev-fixtures.sql` for richer dev data|

## Miniflare Local D1 vs Wrangler Local D1

| Aspect              | Miniflare in-process D1        | Wrangler `--local` D1                |
|---------------------|-------------------------------|---------------------------------------|
| Speed               | Fastest (in-memory)           | Moderate (file-based SQLite)          |
| Persistence         | Lost on process exit           | Persists in `.wrangler/state/`        |
| Reset strategy      | `db.exec()` in `beforeEach`   | Re-run seed SQL file                  |
| Parallelism         | Each vitest worker gets own DB | Shared file — needs worker ID prefix  |
| Fidelity            | High (uses same SQLite engine) | Identical to production D1 API        |

## Anti-patterns

- Seeding once in `beforeAll` and mutating D1 across tests without resetting — test order dependency corrupts results.
- Using autoincrement IDs in seed data without explicit values — IDs drift after delete/insert cycles, breaking FK references.
- Truncating only one table when FKs exist — leaves orphaned rows that cause constraint errors in subsequent tests.
- Pointing Miniflare D1 at a shared file path in parallel vitest workers — concurrent writes corrupt the SQLite file.
- Including seed data in the production migration files — test fixtures must never reach production D1.

## Gotchas

- `db.exec()` in Miniflare runs multi-statement SQL as a single transaction; a single syntax error rolls back all inserts.
- Miniflare 3.x `getD1Database("DB")` returns a `D1Database` stub; the name must exactly match the `d1Databases` array entry.
- `wrangler d1 execute --local` writes to `.wrangler/state/v3/d1/<hash>/`; delete this directory to fully reset local state.
- D1 foreign key enforcement is off by default in SQLite; send `PRAGMA foreign_keys = ON;` at the top of the seed file to test constraint correctness.
- Parallel vitest shards each need an isolated Miniflare instance; do not share a single `mf` across vitest `--shard` workers.

## Verification

```bash
# Confirm local D1 has the expected fixture rows after seeding
wrangler d1 execute example project-db --local \
  --command="SELECT COUNT(*) as n FROM tracks;"
# Expected: n = 3

# Run integration tests and confirm all pass with fresh fixtures
npx vitest run tests/integration/ --reporter=verbose

# Verify idempotency: seed twice, count should still be 3
wrangler d1 execute example project-db --local --file=db/seeds/test-fixtures.sql
wrangler d1 execute example project-db --local --file=db/seeds/test-fixtures.sql
wrangler d1 execute example project-db --local --command="SELECT COUNT(*) FROM tracks;"
```

## Related

- `d1-testing-local.md`
- `miniflare-d1-integration-testing.md`
- `database-seeding-tests.md`
- `test-database-isolation.md`
- `workers-test-patterns.md`
- `transactional-test-rollback.md`

## Sources

- https://developers.cloudflare.com/d1/reference/local-development/
- https://developers.cloudflare.com/workers/wrangler/commands/#d1
- https://miniflare.dev/storage/d1
- https://developers.cloudflare.com/d1/migrations/
