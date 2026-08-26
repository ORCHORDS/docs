# Git Branching Strategy Aligned with Cloudflare Pages Preview Deployments

Date:   2026-08-22
Author: example.com
Status: stable

## Symptom

Feature branches accumulate stale Cloudflare Pages preview deployments
that consume build minutes and clutter the dashboard. D1 migration testing
on feature branches is done against the production database. Preview URLs
are shared in PR comments manually, and broken previews are not noticed
until a reviewer follows a link that errors.

## Context

Cloudflare Pages automatically creates a preview deployment for every
branch push and generates a deterministic URL based on the branch name.
This behaviour can be aligned with a trunk-based or GitFlow branching
strategy to give each PR its own isolated frontend URL and, with care,
an isolated D1 database for migration testing.

Workers deployed via Wrangler do NOT automatically preview — you must
explicitly deploy to a named `env` in `wrangler.toml`. The strategy below
uses Cloudflare Pages branch previews for the UI and per-branch Worker
preview environments for the backend.

---

## 1. Branch Model

```
main ──────────────────────────────────────────────────── production
  │
  ├── release/1.4 ────────────────────────────────────── staging
  │
  ├── feat/user-auth ─────── PR #<number> ──────────────────── preview
  │
  ├── feat/r2-uploads ────── PR #<number> ──────────────────── preview
  │
  └── fix/session-leak ───── PR #<number> ──────────────────── preview
```

```
┌─────────────────┬───────────────────────────────────┬────────────┐
│ Branch pattern  │ Pages URL                         │ Worker env │
├─────────────────┼───────────────────────────────────┼────────────┤
│ main            │ my-project.pages.dev              │ production │
│ release/*       │ release-*.my-project.pages.dev    │ staging    │
│ feat/*, fix/*   │ feat-*.my-project.pages.dev       │ preview    │
└─────────────────┴───────────────────────────────────┴────────────┘
```

Cloudflare Pages transforms `/` and `.` in branch names to `-` for the
subdomain. `feat/user-auth` becomes `feat-user-auth.my-project.pages.dev`.

---

## 2. Cloudflare Pages Branch Configuration

In the Pages project dashboard (or via Wrangler):

```
Build & deployments → Branch control:

  Production branch:       main
  Preview branches:        All non-production branches
  Branch alias (optional): release/* → staging.my-project.pages.dev
```

To configure branch aliases programmatically:

```bash
wrangler pages project edit my-project \
  --production-branch main
```

Custom domain aliases for `release/*` branches require a DNS CNAME entry
and must be configured per-branch in the dashboard or via the Pages API.
Automate this with a GitHub Actions step in the release branch workflow:

```bash
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/my-project/domains" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "staging.my-project.com"}'
```

---

## 3. Worker Preview Environments in wrangler.toml

```toml
name = "my-project-api"
main = "src/index.ts"
compatibility_date = "2024-09-23"

# --- Production ---
[env.production]
vars = { ENVIRONMENT = "production" }

[[env.production.d1_databases]]
binding     = "DB"
database_name = "my-project-prod"
database_id   = "aaaa-bbbb-cccc-dddd-eeee"

# --- Staging (release/* branches) ---
[env.staging]
vars = { ENVIRONMENT = "staging" }

[[env.staging.d1_databases]]
binding     = "DB"
database_name = "my-project-staging"
database_id   = "1111-2222-3333-4444-5555"

# --- Preview (feat/*, fix/* branches) ---
[env.preview]
vars = { ENVIRONMENT = "preview" }

[[env.preview.d1_databases]]
binding     = "DB"
database_name = "my-project-preview"
database_id   = "aaaa-1111-bbbb-2222-cccc"
```

Feature branches share the single `my-project-preview` D1 database.
For strict isolation between PRs, provision a database per PR (see section
5) and inject the `database_id` via a `--binding` override at deploy time.

---

## 4. GitHub Actions: Branch-Based Deploy Routing

```yaml
# .github/workflows/preview.yml
name: Preview Deploy

on:
  push:
    branches-ignore: [main, 'release/**']

jobs:
  deploy-preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm exec turbo run build

      - name: Deploy Worker (preview)
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: |
          pnpm exec wrangler deploy \
            --config worker/wrangler.toml \
            --env preview

      - name: Deploy Pages (preview branch)
        env:
          CLOUDFLARE_API_TOKEN:  ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          BRANCH_SLUG=$(echo "${{ github.ref_name }}" \
            | tr '/' '-' | tr '.' '-' | tr '[:upper:]' '[:lower:]')

          pnpm exec wrangler pages deploy frontend/.next/standalone \
            --project-name=my-project \
            --branch="${{ github.ref_name }}"

          echo "Preview URL: https://${BRANCH_SLUG}.my-project.pages.dev"
          echo "PREVIEW_URL=https://${BRANCH_SLUG}.my-project.pages.dev" \
            >> "$GITHUB_ENV"

      - name: Post preview URL to PR
        if: github.event_name == 'pull_request'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh pr comment "${{ github.event.pull_request.number }}" \
            --body "Preview deployed: $PREVIEW_URL" \
            --edit-last || \
          gh pr comment "${{ github.event.pull_request.number }}" \
            --body "Preview deployed: $PREVIEW_URL"
```

---

## 5. Per-PR D1 Migration Testing

Testing D1 migrations in isolation prevents feature branches from
corrupting a shared preview database. Use the D1 API to provision a
throw-away database per PR:

```bash
# In the PR workflow:
DB_NAME="pr-${{ github.event.pull_request.number }}-db"

DB_ID=$(pnpm exec wrangler d1 create "$DB_NAME" \
  --json 2>/dev/null | jq -r '.uuid')

# Apply migrations to the fresh DB:
pnpm exec wrangler d1 migrations apply "$DB_NAME" --remote

# Deploy the Worker with the per-PR database:
pnpm exec wrangler deploy \
  --env preview \
  --binding "DB=$DB_ID"
```

Clean up the PR database when the PR is closed:

```yaml
# .github/workflows/pr-cleanup.yml
on:
  pull_request:
    types: [closed]

jobs:
  cleanup:
    runs-on: ubuntu-latest
    steps:
      - name: Delete preview D1 database
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: |
          DB_NAME="pr-${{ github.event.pull_request.number }}-db"
          pnpm exec wrangler d1 delete "$DB_NAME" --skip-confirmation || true
```

---

## 6. Cleanup of Stale Preview Deployments

Cloudflare Pages retains all deployments indefinitely. Use the Pages API
to purge deployments older than N days for merged branches:

```bash
#!/usr/bin/env bash
# scripts/cleanup-previews.sh
# Run weekly via a GitHub Actions scheduled job.

ACCOUNT_ID="$CF_ACCOUNT_ID"
PROJECT="my-project"
TOKEN="$CF_API_TOKEN"
CUTOFF=$(date -d '30 days ago' +%s)

curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/pages/projects/$PROJECT/deployments?per_page=100" \
  -H "Authorization: Bearer $TOKEN" | \
  jq -r --argjson cutoff "$CUTOFF" \
    '.result[] | select(
       .environment == "preview" and
       (.created_on | fromdateiso8601) < $cutoff
     ) | .id' | \
  while read -r DEPLOY_ID; do
    echo "Deleting deployment $DEPLOY_ID"
    curl -s -X DELETE \
      "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/pages/projects/$PROJECT/deployments/$DEPLOY_ID" \
      -H "Authorization: Bearer $TOKEN" | jq '.success'
  done
```

Schedule it in GitHub Actions:

```yaml
on:
  schedule:
    - cron: '0 3 * * 1'   # Every Monday at 03:00 UTC
```

---

## Anti-patterns

- Using `main` as both the production branch and a target for in-flight
  feature work. Any push to `main` triggers a production deploy; protect
  it with branch protection rules and required PR reviews.
- Sharing a single preview D1 database across all feature branches. Two
  migrations that add the same column from different branches will
  conflict.
- Hard-coding the preview Worker URL in the frontend `.env` files. The
  URL should be injected at deploy time via the Pages environment variable
  configuration or a build-time `NEXT_PUBLIC_API_URL` override.
- Deleting a branch in Git without cleaning up the Cloudflare Pages
  preview deployment or the per-PR D1 database. Automate cleanup on
  `pull_request: [closed]`.
- Running `wrangler d1 migrations apply --remote` against the production
  database from a feature branch CI job. Gate remote migration runs on
  `github.ref == 'refs/heads/main'`.

---

## Gotchas

- Cloudflare Pages branch aliases (e.g., `staging.my-project.com`) only
  work for the most recent deployment on that branch, not historical ones.
- `wrangler pages deploy --branch` creates a new preview deployment each
  push; it does not replace the previous one. Old deployments accumulate
  and must be cleaned up (see section 6).
- The deterministic preview URL (`feat-user-auth.my-project.pages.dev`)
  is only available after the first deploy of that branch. A new branch
  with no prior deploy has no URL until the first Pages build completes.
- `wrangler d1 delete` requires `--skip-confirmation` for non-interactive
  use in CI. Without it, the command waits for stdin input and hangs.
- Workers `--env preview` shares the same route bindings as production
  unless you explicitly configure `[env.preview.routes]`. Without routes,
  the preview Worker does not intercept any real traffic.

---

## Verification

```bash
# List all active Pages deployments for the project:
wrangler pages deployment list --project-name=my-project

# Confirm the branch preview URL is live:
curl -sI "https://feat-user-auth.my-project.pages.dev/" \
  | head -5

# Check which D1 databases exist (find stale PR databases):
wrangler d1 list | grep '^pr-'

# Verify the preview Worker is using the correct DB binding:
wrangler deployments list --name my-project-api --env preview \
  | head -5
```

---

## Related

- documentation/docs/policies/worktree/github-actions-wrangler-deploy-pipeline.md
- documentation/docs/policies/worktree/pr-readiness-checklist-workers-projects.md
- documentation/docs/policies/worktree/monorepo-workspace-cloudflare-workers.md
- documentation/docs/policies/worktree/conventional-commits-automated-changelog.md

---

## Source URLs

- https://developers.cloudflare.com/pages/configuration/branch-build-controls/
- https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/
- https://developers.cloudflare.com/d1/wrangler-commands/#d1-create
- https://developers.cloudflare.com/api/resources/pages/subresources/deployments/
- https://developers.cloudflare.com/workers/wrangler/environments/
