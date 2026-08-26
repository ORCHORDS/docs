# Wrangler Pages Direct Upload CI Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your CI pipeline must publish a Cloudflare Pages project from a pre-built `dist/` directory without relying on Cloudflare's build environment. You want deterministic builds in GitHub Actions (or any CI system) and need the direct-upload flow (`wrangler pages deploy`) rather than a connected Git integration.

## Context

Cloudflare Pages supports two deployment modes: (1) Git-connected builds where Cloudflare runs the build, and (2) direct uploads where CI produces the artifact and Wrangler pushes it. Direct uploads give you full control over Node version, build cache, environment secrets, and toolchain. `wrangler pages deploy <dir>` targets this path and optionally creates a new deployment or promotes to production via `--branch main`.

---

## Setting Up the Wrangler Pages Project

```toml
# wrangler.toml — only needed for Pages projects with Functions
name = "my-app"
pages_build_output_dir = "dist"
compatibility_date = "2026-01-01"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding = "DB"
database_name = "my-app-prod"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

For static-only Pages projects, `wrangler.toml` is optional — `wrangler pages deploy dist/` is sufficient.

---

## GitHub Actions Workflow

```yaml
# .github/workflows/pages-deploy.yml
name: Deploy to Cloudflare Pages

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      deployments: write   # required for GitHub Deployments status

    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - name: Install dependencies
        run: pnpm install --frozen-lockfile

      - name: Build
        run: pnpm build
        env:
          NODE_ENV: production

      - name: Deploy to Pages
        run: |
          pnpm wrangler pages deploy dist/ \
            --project-name "$PROJECT_NAME" \
            --branch "$BRANCH_NAME" \
            --commit-hash "${{ github.sha }}" \
            --commit-message "${{ github.event.head_commit.message }}"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          PROJECT_NAME: my-app
          BRANCH_NAME: ${{ github.ref_name }}
```

---

## Promoting Preview to Production

```yaml
# Separate job — runs only on main after preview succeeds
promote-production:
  needs: deploy
  if: github.ref == 'refs/heads/main'
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - run: pnpm wrangler pages deploy dist/ \
               --project-name my-app \
               --branch main
      env:
        CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

Deploying with `--branch main` marks the deployment as production in the Cloudflare dashboard.

---

## Scoped API Token Permissions

Create a token with the minimum required permissions instead of a Global API Key:

```
Permissions required:
  - Cloudflare Pages: Edit
  - Account: Read (to resolve account ID)

Optional (if using D1/R2 bindings in Pages Functions):
  - D1: Edit
  - Workers R2 Storage: Edit
```

Store as `CLOUDFLARE_API_TOKEN` in GitHub Actions secrets. The `CLOUDFLARE_ACCOUNT_ID` can be read from the dashboard URL or `wrangler whoami`.

---

## Extracting the Deployment URL

```yaml
- name: Deploy and capture URL
  id: deploy
  run: |
    OUTPUT=$(pnpm wrangler pages deploy dist/ \
      --project-name my-app \
      --branch "${{ github.ref_name }}" 2>&1)
    echo "$OUTPUT"
    DEPLOY_URL=$(echo "$OUTPUT" | grep -oP 'https://[a-z0-9\-]+\.pages\.dev')
    echo "url=$DEPLOY_URL" >> "$GITHUB_OUTPUT"
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

- name: Comment PR with preview URL
  if: github.event_name == 'pull_request'
  uses: actions/github-script@v7
  with:
    script: |
      github.rest.issues.createComment({
        issue_number: context.issue.number,
        owner: context.repo.owner,
        repo: context.repo.repo,
        body: `Preview: ${{ steps.deploy.outputs.url }}`
      })
```

---

## Anti-patterns

- Using `CLOUDFLARE_GLOBAL_API_KEY` + `CLOUDFLARE_EMAIL` — prefer scoped tokens; global keys are overprivileged.
- Running `wrangler pages deploy` without `--branch` — defaults to a random preview alias, never promotes to production.
- Skipping `--commit-hash` — makes deployments untrackable in the Cloudflare dashboard history.
- Deploying the project root instead of the build output directory — uploads source files and `node_modules`.
- Running deploy on every PR commit before the build passes — add `needs: build` to gate on build success.

---

## Gotchas

- `wrangler pages deploy` exits 0 even on partial failures (Functions compile errors) in some Wrangler versions — parse stdout for `Error:` lines.
- The `--project-name` must exactly match an existing project in your account; it does not create one automatically.
- Branch-based preview URLs follow the pattern `<branch>.<project>.pages.dev` with sanitized names — hyphens replace slashes.
- If `wrangler.toml` defines `pages_build_output_dir`, you must still pass the directory explicitly to `wrangler pages deploy` — the config key is for the connected-Git mode only.
- `CLOUDFLARE_ACCOUNT_ID` is optional if the token is scoped to a single account, but recommended to avoid ambiguity in multi-account setups.

---

## Verification

```bash
# Verify project exists and list recent deployments
pnpm wrangler pages deployment list --project-name my-app

# Check a specific deployment status
pnpm wrangler pages deployment tail <deployment-id> --project-name my-app

# Confirm the production alias points to latest
curl -sI https://my-app.pages.dev | grep cf-ray
```

---

## Related

- `wrangler-config-validation-ci.md` — validate `wrangler.toml` before deploy
- `wrangler-d1-migrations-local-dev-workflow.md` — D1 migration strategy for Pages Functions
- `wrangler-secret-bulk-import-script.md` — managing secrets for Pages projects
- `playwright-e2e-workers-wrangler-dev.md` — E2E testing against Pages preview URLs
- `lighthouse-ci-performance-budget-github-actions.md` — run Lighthouse against the deployed URL

---

## Sources

- Cloudflare Pages Direct Upload docs: https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/
- Wrangler CLI reference: https://developers.cloudflare.com/workers/wrangler/commands/#pages
- GitHub Deployments API: https://docs.github.com/en/rest/deployments/deployments
