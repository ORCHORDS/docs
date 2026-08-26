# Cloudflare Pages Branch Deploy Preview D1 Seeding

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Cloudflare Pages preview deployments spin up per-branch environments automatically,
but they share no database state with production and arrive with an empty D1
database. For example project / example.com, reviewers who open a preview branch see a
blank feed with no anonymous posts, no moderation queue, and no seed content to
exercise the UI. The preview is useless for feature review until D1 is seeded with
representative fixture data that matches the current schema.

## Context

Pages preview deployments inherit the D1 binding declared in `wrangler.toml` or
the Pages project settings. Because previews create isolated deployments rather
than isolated databases, teams must either bind previews to a dedicated seed
database or run a seed script against the preview's D1 binding after the deployment
URL is known. Wrangler's `d1 execute` command can target a remote database by ID,
making it possible to automate seeding in the same GitHub Actions workflow that
Pages uses for branch deployments.

## Section 1 — dedicated preview D1 database per environment

Use a separate D1 database for preview deployments rather than sharing the
production or staging database. Configure the preview binding in the Pages project's
environment settings via the dashboard or Wrangler.

```toml
# wrangler.toml (Pages project)
name = "example project-frontend"
pages_build_output_dir = "dist"

[[d1_databases]]
binding = "DB"
database_name = "example project-prod"
database_id = "prod-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[env.preview]
[[env.preview.d1_databases]]
binding = "DB"
database_name = "example project-preview"
database_id = "prev-yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
```

Create the preview database once if it does not exist:

```bash
npx wrangler d1 create example project-preview
# Copy the returned database_id into wrangler.toml [env.preview]
```

## Section 2 — seed script and fixture data

Keep seed fixtures in `scripts/seed/` as SQL files. The seed must be idempotent —
safe to run on an already-seeded database so re-deployments on the same branch do
not produce duplicate rows.

```sql
-- scripts/seed/example project-preview.sql
-- Idempotent seed: upsert anonymous posts for preview review

CREATE TABLE IF NOT EXISTS posts (
  id TEXT PRIMARY KEY,
  content TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER,
  flagged INTEGER DEFAULT 0
);

INSERT OR IGNORE INTO posts (id, content, created_at, expires_at, flagged) VALUES
  ('seed-001', 'Welcome to example project preview — this is a seeded post.', 1753920000, NULL, 0),
  ('seed-002', 'Anonymous discussion thread for feature branch testing.', 1753920060, NULL, 0),
  ('seed-003', 'Flagged post example for moderation queue preview.', 1753920120, NULL, 1),
  ('seed-004', 'Expired post — should not appear in active feed.', 1700000000, 1700086400, 0),
  ('seed-005', 'Post with long content to test truncation rendering in UI components. '
               || 'This content intentionally exceeds a single line of display width.',
               1753920180, NULL, 0);
```

```bash
# scripts/seed-preview.sh
#!/usr/bin/env bash
set -euo pipefail

DB_ID="${PREVIEW_D1_DATABASE_ID:?Must set PREVIEW_D1_DATABASE_ID}"
echo "Seeding preview D1 database: $DB_ID"

npx wrangler d1 execute "$DB_ID" \
  --remote \
  --file scripts/seed/example project-preview.sql

echo "Seed complete."
```

## Section 3 — GitHub Actions integration with Pages deployment

Wire the seed step into the Pages deployment workflow so every branch preview
is seeded automatically after the Pages deployment URL is confirmed.

```yaml
# .github/workflows/preview-deploy.yml
name: Pages Preview Deploy + D1 Seed

on:
  pull_request:
    branches: [main]

jobs:
  deploy-preview:
    name: Deploy Pages preview
    runs-on: ubuntu-latest
    outputs:
      preview_url: ${{ steps.pages-deploy.outputs.url }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - run: npm ci
      - run: npm run build

      - name: Deploy Pages preview
        id: pages-deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          OUTPUT=$(npx wrangler pages deploy dist \
            --project-name example project-frontend \
            --branch "${{ github.head_ref }}" \
            2>&1)
          echo "$OUTPUT"
          URL=$(echo "$OUTPUT" | grep -oP 'https://[^\s]+\.pages\.dev' | tail -1)
          echo "url=$URL" >> "$GITHUB_OUTPUT"

      - name: Seed preview D1 database
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          PREVIEW_D1_DATABASE_ID: ${{ secrets.PREVIEW_D1_DATABASE_ID }}
        run: bash scripts/seed-preview.sh

      - name: Post preview URL to PR
        uses: actions/github-script@v7
        with:
          script: |
            const url = '${{ steps.pages-deploy.outputs.preview_url }}';
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `**Preview deployed:** ${url}\n\nD1 preview database seeded with fixture data.`
            });
```

## Section 4 — rollback and reset

If the seed corrupts preview data or a schema migration breaks the seed fixtures,
reset the preview database to a clean state:

```bash
# Drop all preview tables and re-seed from scratch
npx wrangler d1 execute "$PREVIEW_D1_DATABASE_ID" \
  --remote \
  --command "DROP TABLE IF EXISTS posts; DROP TABLE IF EXISTS sessions;"

bash scripts/seed-preview.sh

echo "Preview D1 reset and re-seeded."
```

For schema changes that alter the seed SQL, update `scripts/seed/example project-preview.sql`
in the same PR that changes the schema migration file. The `CREATE TABLE IF NOT
EXISTS` pattern ensures backward compatibility when the seed runs before migrations.
Run migrations first, then seed:

```bash
npx wrangler d1 migrations apply example project-preview --remote
bash scripts/seed-preview.sh
```

## Anti-patterns

- Binding preview deployments to the production D1 database — seed data will
  pollute production rows and real-user data may appear in branch previews
- Storing seed SQL inline in the GitHub Actions YAML instead of a versioned file —
  makes diffs hard to review and breaks the idempotency guarantee
- Running the seed before the Pages deployment is confirmed live — the deployment
  may fail and the seed wasted
- Using `DELETE FROM` + `INSERT` in the seed instead of `INSERT OR IGNORE` —
  causes data loss if the seed runs twice on an active preview
- Hardcoding the preview D1 database ID in `wrangler.toml` without using an
  environment variable — rotations require a toml commit

## Gotchas

- Pages preview deployments generate a new URL per commit, not per branch — the
  URL grep in the workflow must use `tail -1` to get the latest URL for the branch
- `wrangler d1 execute --remote` requires the database ID, not the binding name;
  store the preview database ID in a repository secret
- D1 preview databases are not automatically deleted when a branch is deleted —
  add a `pull_request: types: [closed]` workflow step to optionally clear the
  preview database
- The `[env.preview]` D1 binding in `wrangler.toml` applies to Wrangler-managed
  Workers deployments; Pages environment bindings are set separately in the Pages
  project dashboard or via the Pages API

## Verification

1. Open a pull request — the Actions workflow should complete with a Pages preview
   URL posted as a PR comment.
2. Navigate to the preview URL and verify the seeded posts appear in the feed.
3. Check that the flagged post (`seed-003`) appears in the moderation queue UI.
4. Confirm the expired post (`seed-004`) does NOT appear in the active post feed.
5. Re-run the seed script manually — verify row count does not change (idempotent).

## Related

- `/documentation/categories/deploy/cloudflare-pages-preview-deployments.md`
- `/documentation/categories/deploy/d1-schema-migration-sequencing-wrangler-remote.md`
- `/documentation/categories/deploy/kv-namespace-seed-automation-wrangler.md`
- `/documentation/categories/deploy/workers-d1-pre-deploy-migration-safety.md`

## Sources

- https://developers.cloudflare.com/pages/configuration/preview-deployments/
- https://developers.cloudflare.com/d1/get-started/#interact-with-your-d1-database
- https://developers.cloudflare.com/workers/wrangler/commands/#d1
- https://developers.cloudflare.com/pages/configuration/build-configuration/
