# GitHub Actions — Cloudflare Deploy Workflow

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A push to `main` or a staging branch triggers no Cloudflare Pages
build, or the Worker deploy step fails with "Authentication error"
or "D1 database not found" before the Pages asset upload even
starts.

## Context

example project ships a Next.js static export (`output: "export"`) to
Cloudflare Pages and a Cloudflare Worker for the API layer, with
D1 as the relational store and R2 for object storage. Deployments
run from GitHub Actions using `cloudflare/wrangler-action` for
Workers and the Cloudflare Pages GitHub integration or a direct
Wrangler Pages deploy step. Environment-gated workflows separate
staging from production.

## 1. Secrets and Environment Variables

Store exactly two secrets at the repository or environment level.
Never put them in workflow `env:` blocks as plaintext.

| Secret name              | Where to set          | Scope            |
|--------------------------|-----------------------|------------------|
| `CF_API_TOKEN`           | Environment secret    | Deploy only      |
| `CLOUDFLARE_ACCOUNT_ID`  | Repository variable   | All workflows    |

Create the API token in the Cloudflare dashboard under
**My Profile → API Tokens → Create Token**. Use the
"Edit Cloudflare Workers" template and scope it to the target
account. For Pages deploys add the "Cloudflare Pages:Edit"
permission to the same token.

```yaml
env:
  CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
  CLOUDFLARE_ACCOUNT_ID: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
```

## 2. D1 Migration Step Before Deploy

Run `wrangler d1 migrations apply` before uploading Worker code.
A failed migration should abort the deploy; the `--remote` flag
targets the bound D1 database for the environment.

```yaml
- name: Apply D1 migrations (staging)
  if: github.ref == 'refs/heads/staging'
  run: |
    pnpm wrangler d1 migrations apply example project_DB \
      --remote \
      --env staging
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    CLOUDFLARE_ACCOUNT_ID: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
```

Use a separate named database binding per environment in
`wrangler.toml`:

```toml
[env.staging]
[[env.staging.d1_databases]]
binding = "example project_DB"
database_name = "example project-staging"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[env.production]
[[env.production.d1_databases]]
binding = "example project_DB"
database_name = "example project-production"
database_id   = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
```

## 3. Wrangler Action for Workers Deploy

Pin `cloudflare/wrangler-action` to a specific major version tag
so upstream changes do not break the pipeline silently.

```yaml
- name: Deploy Worker
  uses: cloudflare/wrangler-action@v3
  with:
    apiToken: ${{ secrets.CF_API_TOKEN }}
    accountId: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
    command: deploy --env ${{ inputs.cf_env }}
    workingDirectory: apps/api
    packageManager: pnpm
```

The `command` field passes arguments directly to `wrangler`, so
`deploy --env staging` selects the `[env.staging]` block from
`wrangler.toml`. Do not embed the token in `command:`.

## 4. Cloudflare Pages Deploy Step

For the static export, build the Next.js app then upload the
`out/` directory using `wrangler pages deploy`.

```yaml
- name: Build Next.js export
  run: pnpm --filter web build
  env:
    NEXT_PUBLIC_API_URL: ${{ vars.API_URL_STAGING }}

- name: Deploy to Cloudflare Pages (staging)
  uses: cloudflare/wrangler-action@v3
  with:
    apiToken: ${{ secrets.CF_API_TOKEN }}
    accountId: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
    command: >
      pages deploy apps/web/out
      --project-name example project-staging
      --commit-dirty=true
```

Set `--branch` explicitly when the Pages project is not linked to
the repository so Cloudflare knows which preview URL to assign.

## 5. pnpm Build Cache

Cache the pnpm store across runs to keep install times under
30 seconds in a monorepo.

```yaml
- name: Setup pnpm
  uses: pnpm/action-setup@v4
  with:
    version: 9

- name: Cache pnpm store
  uses: actions/cache@v4
  with:
    path: ~/.local/share/pnpm/store
    key: pnpm-${{ runner.os }}-${{ hashFiles('**/pnpm-lock.yaml') }}
    restore-keys: pnpm-${{ runner.os }}-

- name: Install dependencies
  run: pnpm install --frozen-lockfile
```

## 6. Staging vs Production Environment Gates

Wrap the production deploy job in a GitHub environment that
requires manual approval. The staging job runs automatically on
every push to `main`; production waits for a reviewer to approve.

```yaml
jobs:
  deploy-staging:
    environment: staging
    runs-on: ubuntu-latest
    steps: [...]

  deploy-production:
    needs: deploy-staging
    environment:
      name: production
      url: https://app.example project.io
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps: [...]
```

Configure the `production` environment in **Settings →
Environments** with at least one required reviewer and a 5-minute
wait timer.

## Anti-patterns

- Storing `CF_API_TOKEN` in a plain `env:` block at the workflow
  level — it leaks into all job logs and child processes.
- Running D1 migrations inside the same shell command as the
  Worker deploy; on migration failure the Worker is deployed with
  a mismatched schema.
- Using the Cloudflare Pages GitHub integration (automatic builds)
  alongside a workflow-driven deploy — they race and produce
  duplicate deployments.
- Hard-coding `database_id` values in workflow YAML instead of
  `wrangler.toml`; the IDs belong to infrastructure config, not
  CI scripts.

## Gotchas

- `wrangler pages deploy` exits 0 even when the upload partially
  fails if `--commit-dirty=true` is set; always check the job
  summary URL for the canonical deploy status.
- `pnpm install --frozen-lockfile` fails when `pnpm-lock.yaml`
  is out of date; add a `pnpm install` step in a PR check that
  commits the lockfile update before merge.
- The Cloudflare API token must have "Account:D1:Edit" in
  addition to the Pages/Workers permissions for the migration
  step to succeed.
- Environment secrets are not available to jobs that reference
  a different environment name; staging and production must each
  have their own `CF_API_TOKEN` secret.

## Verification

```bash
# Confirm the Worker is live at the staging route
curl -s https://api-staging.example project.io/health | jq .

# Confirm the Pages project shows the latest deploy
pnpm wrangler pages deployment list --project-name example project-staging

# Confirm D1 schema is at the latest migration version
pnpm wrangler d1 migrations list example project_DB --remote --env staging
```

## Related

- documentation/docs/policies/github/github-environments-deployment-protection-rules.md
- documentation/docs/policies/deploy/cloudflare-pages-deploy-pipeline.md
- documentation/docs/policies/cloudflare/wrangler-d1-migrations.md
- documentation/docs/policies/cloudflare/workers-secrets-env-vars.md

## Source URLs (verified 2026-08-17)

- https://github.com/cloudflare/wrangler-action
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/
- https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
