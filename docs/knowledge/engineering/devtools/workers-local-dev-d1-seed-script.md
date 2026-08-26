# D1 Seed Scripts for Local Wrangler Dev

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

When running `wrangler dev` locally, the D1 database starts empty and each developer must manually insert fixtures before they can exercise any data-dependent code path. A repeatable `scripts/seed.ts` script — wired into an npm script and a Vitest `globalSetup` hook — ensures every dev environment and every test run begins with a consistent, known data set.

---

## Context

Cloudflare D1 in local mode stores its SQLite file under `.wrangler/state/`. `wrangler d1 execute --local` lets you run arbitrary SQL against that file without an API token, making it safe to use in offline development. Running `--file=schema.sql` first drops and recreates all tables so the seed always starts from a clean slate. The seed script itself uses the Cloudflare REST API (via `@cloudflare/d1` — or simply shells out to `wrangler d1 execute`) so it can target either local or remote databases from the same code. Vitest's `globalSetup` hook runs once before the test suite, giving each test a fully-seeded local D1 without boilerplate in individual test files.

---

## Config / Setup

```toml
# wrangler.toml
name = "my-worker"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding  = "DB"
database_name = "my-app-db"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # production ID
```

```jsonc
// package.json
{
  "scripts": {
    "dev"       : "wrangler dev",
    "db:reset"  : "wrangler d1 execute my-app-db --local --file=schema.sql",
    "db:seed"   : "tsx scripts/seed.ts",
    "db:fresh"  : "npm run db:reset && npm run db:seed",
    "test"      : "vitest run"
  },
  "devDependencies": {
    "tsx"               : "^4.16.0",
    "vitest"            : "^1.6.0",
    "@cloudflare/vitest-pool-workers": "^0.5.0"
  }
}
```

```yaml
# vitest.config.ts (excerpt)
# globalSetup runs once before all tests; see Implementation section
globalSetup: ['./scripts/vitest-global-setup.ts']
```

---

## Implementation — Seed Script

```typescript
// scripts/seed.ts
// Run with: tsx scripts/seed.ts [--remote]
import { execSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const isRemote = process.argv.includes('--remote');
const DB_NAME  = 'my-app-db';
const ROOT     = resolve(import.meta.dirname, '..');

function wranglerD1(sql: string, label: string): void {
  const target = isRemote ? '' : '--local';
  const tmp = `/tmp/seed-${Date.now()}.sql`;
  // Write SQL to a temp file so we avoid shell-escaping issues
  const { writeFileSync, unlinkSync } = await import('node:fs').then(m => m);
  require('node:fs').writeFileSync(tmp, sql, 'utf8');
  try {
    console.log(`[seed] ${label}`);
    execSync(
      `wrangler d1 execute ${DB_NAME} ${target} --file=${tmp}`,
      { stdio: 'inherit', cwd: ROOT }
    );
  } finally {
    require('node:fs').unlinkSync(tmp);
  }
}

// 1. Reset schema
console.log('[seed] Applying schema …');
execSync(
  `wrangler d1 execute ${DB_NAME} ${isRemote ? '' : '--local'} --file=${ROOT}/schema.sql`,
  { stdio: 'inherit', cwd: ROOT }
);

// 2. Seed users
const usersSql = `
INSERT INTO users (id, email, name, created_at) VALUES
  ('usr_1', 'alice@example.com', 'Alice',   '2024-01-01T00:00:00Z'),
  ('usr_2', 'bob@example.com',   'Bob',     '2024-01-02T00:00:00Z'),
  ('usr_3', 'carol@example.com', 'Carol',   '2024-01-03T00:00:00Z')
ON CONFLICT (id) DO NOTHING;
`;
execSync(
  `wrangler d1 execute ${DB_NAME} ${isRemote ? '' : '--local'} --command="${usersSql.replace(/\n/g, ' ').trim()}"
`,
  { stdio: 'inherit', cwd: ROOT }
);

// 3. Seed products
const seedFile = resolve(ROOT, 'fixtures', 'products.sql');
if (require('node:fs').existsSync(seedFile)) {
  execSync(
    `wrangler d1 execute ${DB_NAME} ${isRemote ? '' : '--local'} --file=${seedFile}`,
    { stdio: 'inherit', cwd: ROOT }
  );
}

console.log('[seed] Done.');
```

```typescript
// scripts/vitest-global-setup.ts
import { execSync } from 'node:child_process';
import { resolve } from 'node:path';

const ROOT    = resolve(import.meta.dirname, '..');
const DB_NAME = 'my-app-db';

export async function setup(): Promise<void> {
  console.log('\n[globalSetup] Resetting local D1 …');
  execSync(
    `wrangler d1 execute ${DB_NAME} --local --file=${ROOT}/schema.sql`,
    { stdio: 'inherit', cwd: ROOT }
  );
  execSync(
    `tsx ${ROOT}/scripts/seed.ts`,
    { stdio: 'inherit', cwd: ROOT }
  );
  console.log('[globalSetup] D1 ready.\n');
}

export async function teardown(): Promise<void> {
  // Optionally wipe local state after the suite
  // execSync(`rm -rf .wrangler/state/d1`, { cwd: ROOT });
}
```

```sql
-- schema.sql (minimal example)
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
  id         TEXT PRIMARY KEY,
  email      TEXT UNIQUE NOT NULL,
  name       TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE products (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  price_cents INTEGER NOT NULL,
  user_id    TEXT NOT NULL REFERENCES users(id)
);
```

---

## CI Integration

```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm

      - run: npm ci

      - name: Apply schema + seed D1 (local)
        run: npm run db:fresh
        # No API token needed for --local; wrangler writes to .wrangler/state/

      - name: Run tests
        run: npm test
        # vitest globalSetup also calls db:fresh, so this step is a belt-and-suspenders
        # reset for cases where tests run without a prior db:fresh.

      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: d1-state
          path: .wrangler/state/d1/
```

---

## Anti-patterns

- **Using `--remote` in CI without a scoped API token** — remote writes against the production D1 database; always gate `--remote` behind an explicit flag and a staging database ID.
- **Embedding multi-line SQL in shell `--command`** — shell escaping of single quotes and newlines is error-prone; write SQL to a temp file and use `--file` instead.
- **Running seed inside individual test files** — this creates race conditions and makes the suite order-dependent; centralise in `globalSetup`.
- **Checking `.wrangler/state/` into git** — add `.wrangler/` to `.gitignore`; it contains binary SQLite files that conflict across branches.

---

## Gotchas

- `wrangler d1 execute --local` requires `wrangler` ≥ 3.39 for reliable `--file` support.
- `import.meta.dirname` is available in Node 22+ and in `tsx` with `--tsconfig` pointing to `moduleResolution: bundler` or `node16`.
- The `ON CONFLICT … DO NOTHING` pattern is idempotent and safe to re-run, unlike plain `INSERT`.
- Vitest `globalSetup` files cannot import Vitest helpers (`expect`, `test`); keep them pure setup/teardown.
- When using `@cloudflare/vitest-pool-workers`, D1 bindings are injected by the pool; `globalSetup` still runs on the Node host, so use `wrangler d1 execute --local` (shell-out) rather than the Worker binding API.

---

## Verification

```bash
# 1. Fresh reset + seed
npm run db:fresh

# 2. Confirm rows exist
wrangler d1 execute my-app-db --local --command="SELECT COUNT(*) FROM users;"

# 3. Run tests (globalSetup will re-seed)
npm test

# 4. Seed against remote staging (requires CF_API_TOKEN)
CLOUDFLARE_API_TOKEN=<token> tsx scripts/seed.ts --remote
```

---

## Related

- `workers-multi-worker-local-dev-service-bindings.md`
- `wrangler-tail-structured-log-parsing.md`

---

## Sources

- Cloudflare D1 local development docs — https://developers.cloudflare.com/d1/best-practices/local-development/
- wrangler d1 execute reference — https://developers.cloudflare.com/workers/wrangler/commands/#d1
- Vitest globalSetup — https://vitest.dev/config/#globalsetup
