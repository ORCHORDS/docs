# D1 Schema Branching for Preview Environments

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your team runs preview deployments per pull request (Cloudflare Pages or
Workers with branch deployments). Each PR may contain a schema migration.
You need an isolated D1 database per preview so migrations can be tested
without touching staging or production data, and the preview database is
destroyed when the PR closes.

## Context

Cloudflare does not yet natively snapshot a D1 database the way Neon branches
a Postgres cluster. The D1 branching pattern is therefore:

1. **Create** a fresh D1 database named after the PR/branch.
2. **Apply** all migrations up to the PR's HEAD.
3. **Seed** with fixture data.
4. **Bind** the preview Worker to this database via wrangler environment
   overrides or a CI-written `wrangler.toml` patch.
5. **Destroy** the database when the PR merges or closes.

This article covers the CI automation, the wrangler binding injection, and
teardown via GitHub Actions.

---

## Naming Convention

Use a deterministic, slug-safe name derived from the PR number:

```
d1-preview-pr-<PR_NUMBER>
```

Example: `d1-preview-pr-42`. Cloudflare D1 database names are limited to
64 characters, alphanumeric plus hyphens.

---

## GitHub Actions: Create & Apply on PR Open/Sync

```yaml
# .github/workflows/preview-d1-create.yml
name: Preview D1 — Create & Migrate

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  preview-db:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - uses: actions/checkout@v4

      - name: Install Wrangler
        run: npm install -g wrangler

      - name: Create preview D1 database
        id: create_db
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          DB_NAME="d1-preview-pr-${{ github.event.pull_request.number }}"
          # Idempotent: ignore error if already exists
          wrangler d1 create "$DB_NAME" 2>/dev/null || true
          DB_ID=$(wrangler d1 info "$DB_NAME" --json | jq -r '.uuid')
          echo "db_id=$DB_ID" >> "$GITHUB_OUTPUT"
          echo "db_name=$DB_NAME" >> "$GITHUB_OUTPUT"

      - name: Apply migrations to preview DB
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          wrangler d1 migrations apply "${{ steps.create_db.outputs.db_name }}" --remote

      - name: Seed preview DB
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          wrangler d1 execute "${{ steps.create_db.outputs.db_name }}" \
            --remote --file ./scripts/seed.sql

      - name: Comment PR with DB info
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `**Preview D1 database:** \`${{ steps.create_db.outputs.db_name }}\`\n` +
                    `**DB ID:** \`${{ steps.create_db.outputs.db_id }}\``
            })
```

---

## Injecting the Preview Binding into Workers

### Option A — Environment Variable Override (wrangler.toml `[env.preview]`)

Add a dynamic `[env.preview]` section in `wrangler.toml` that reads the DB
binding from an environment variable set by CI:

```toml
# wrangler.toml
[env.preview]
# DB_ID is injected by CI via --var or environment override
[[env.preview.d1_databases]]
binding = "DB"
database_name = "d1-preview-pr-0"   # placeholder; overridden by CI
database_id   = "00000000-0000-0000-0000-000000000000"
```

In CI, patch the placeholder before deploying:

```bash
DB_ID="${{ steps.create_db.outputs.db_id }}"
PR="${{ github.event.pull_request.number }}"

# Patch wrangler.toml in-place (requires yq or sed)
sed -i "s|d1-preview-pr-0|d1-preview-pr-${PR}|g" wrangler.toml
sed -i "s|00000000-0000-0000-0000-000000000000|${DB_ID}|g" wrangler.toml

wrangler deploy --env preview
```

### Option B — Programmatic wrangler.toml Generation

```typescript
// scripts/gen-preview-wrangler.ts
import { writeFileSync } from "node:fs";

const prNumber = process.env.PR_NUMBER!;
const dbId     = process.env.DB_ID!;

const config = `
name = "my-worker-preview-pr-${prNumber}"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding       = "DB"
database_name = "d1-preview-pr-${prNumber}"
database_id   = "${dbId}"
`.trim();

writeFileSync("wrangler.preview.toml", config, "utf8");
console.log("Generated wrangler.preview.toml");
```

Deploy with:

```bash
npx tsx scripts/gen-preview-wrangler.ts
wrangler deploy --config wrangler.preview.toml
```

---

## Workers: Detecting Preview vs Production DB

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  ENVIRONMENT: string; // "production" | "preview" | "local"
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (env.ENVIRONMENT === "preview") {
      // Allow destructive test endpoints in preview only
      const url = new URL(request.url);
      if (url.pathname === "/__reset") {
        await resetPreviewData(env.DB);
        return new Response("Preview DB reset.", { status: 200 });
      }
    }
    // Normal request handling…
    return new Response("OK");
  },
};

async function resetPreviewData(db: D1Database): Promise<void> {
  await db.batch([
    db.prepare("DELETE FROM orders"),
    db.prepare("DELETE FROM users"),
  ]);
}
```

---

## GitHub Actions: Destroy on PR Close

```yaml
# .github/workflows/preview-d1-destroy.yml
name: Preview D1 — Destroy

on:
  pull_request:
    types: [closed]

jobs:
  destroy-db:
    runs-on: ubuntu-latest
    steps:
      - name: Install Wrangler
        run: npm install -g wrangler

      - name: Delete preview D1 database
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          DB_NAME="d1-preview-pr-${{ github.event.pull_request.number }}"
          wrangler d1 delete "$DB_NAME" --skip-confirmation 2>/dev/null || echo "DB not found, skipping."
```

---

## Anti-patterns

- **Sharing a single staging D1 database across all PRs**: concurrent PRs with
  conflicting migrations corrupt the shared schema.
- **Using the production `database_id` in `wrangler.toml` and relying on
  per-Worker access control**: preview deployments can still write to
  production if the binding resolves to the wrong DB.
- **Not seeding the preview DB**: preview testing without representative data
  produces false confidence. Always run a seed script after migrations.
- **Leaving preview DBs alive indefinitely**: orphaned databases accumulate
  against account limits. The destroy workflow must run on `types: [closed]`
  which fires for both merged and abandoned PRs.

---

## Gotchas

- `wrangler d1 create` is **not idempotent** — it errors if the name exists.
  Wrap with `|| true` or check `wrangler d1 list` first.
- D1 database names must be unique per account, not per zone. If multiple repos
  use the same naming scheme, prefix with the repo slug: `repo-pr-42`.
- `wrangler d1 delete` requires `--skip-confirmation` in non-interactive CI.
- Preview Workers deployed via `wrangler deploy` to a custom name still
  inherit the account's Worker limit; clean up stale Workers alongside stale
  databases.
- Cloudflare's D1 free tier limits total databases. Monitor with
  `wrangler d1 list --json | jq length`.

---

## Verification

```bash
# Confirm database was created
wrangler d1 list --json | jq '.[] | select(.name | startswith("d1-preview-pr-"))'

# Confirm migrations applied
wrangler d1 migrations list d1-preview-pr-42 --remote

# Confirm Worker binding resolves to preview DB (check wrangler.toml diff)
wrangler d1 info d1-preview-pr-42 --json | jq '{uuid, name}'
```

---

## Related

- `d1-migrations-wrangler-ci-cd.md`
- `d1-schema-versioning-wrangler-migrations.md`
- `d1-ephemeral-test-database-miniflare-teardown.md`
- `d1-seeding-ci-cd-pipelines.md`
- `database-branching-preview.md`

---

## Sources

- Cloudflare D1 docs: https://developers.cloudflare.com/d1/
- Wrangler CLI reference: https://developers.cloudflare.com/workers/wrangler/commands/#d1
- Cloudflare Pages preview deployments: https://developers.cloudflare.com/pages/configuration/preview-deployments/
