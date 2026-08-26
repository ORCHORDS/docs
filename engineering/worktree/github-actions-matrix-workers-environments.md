# GitHub Actions Matrix Strategy for Multi-Environment Workers Deploys

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project deploys to three Cloudflare environments — `preview`, `staging`, and `production` — across five Workers. Running sequential deploy jobs means a full promotion cycle takes 25+ minutes. Simultaneously, different branches target different environments (feature branches → preview, `main` → staging, tags → production), and environment-specific secrets must be injected correctly without cross-contamination. The solution is a GitHub Actions matrix strategy that fans out deploy jobs in parallel while keeping environment secrets isolated per matrix leg.

---

## Context

GitHub Actions matrix strategy generates a set of jobs from a parameter grid, running them concurrently. For Cloudflare Workers, the matrix axis is `environment` (or `[worker, environment]` for a two-dimensional fan-out). Each leg receives the correct Cloudflare API token and Wrangler environment flag via matrix-scoped secrets lookups. This reduces the serial deploy time to the duration of the slowest single Worker deploy rather than the sum of all deploys.

---

## Single-Axis Matrix: Environment Fan-out

Deploy the same Worker to all three environments in parallel:

```yaml
# .github/workflows/deploy-workers.yml
name: Deploy Workers

on:
  push:
    branches: [main]
  release:
    types: [published]

jobs:
  deploy:
    name: Deploy → ${{ matrix.environment }}
    runs-on: ubuntu-latest
    environment: ${{ matrix.environment }}   # GitHub Environment gates

    strategy:
      fail-fast: false    # Don't cancel other legs on a single failure
      matrix:
        environment: [preview, staging, production]
        exclude:
          # Only deploy to production on tagged releases
          - environment: production
        include:
          - environment: production
            ref: ${{ github.ref }}
            condition: ${{ startsWith(github.ref, 'refs/tags/') }}

    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Deploy via Wrangler
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken:    ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId:   ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          command:     deploy --env ${{ matrix.environment }}
          workingDirectory: apps/workers/api-gateway
```

---

## Two-Dimensional Matrix: Worker × Environment

When multiple Workers must be deployed and each combination is independent:

```yaml
jobs:
  deploy:
    name: ${{ matrix.worker }} → ${{ matrix.environment }}
    runs-on: ubuntu-latest
    environment: ${{ matrix.environment }}

    strategy:
      fail-fast: false
      max-parallel: 6         # Cloudflare API rate limit headroom
      matrix:
        worker:
          - api-gateway
          - auth
          - payments
          - assets
          - cron
        environment:
          - preview
          - staging
        include:
          # Production deploys only for api-gateway and auth (others use preview URLs)
          - worker: api-gateway
            environment: production
          - worker: auth
            environment: production

    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Deploy ${{ matrix.worker }} to ${{ matrix.environment }}
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken:    ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId:   ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          command:     deploy --env ${{ matrix.environment }}
          workingDirectory: apps/workers/${{ matrix.worker }}
```

---

## Environment-Specific Secret Injection

GitHub Environments allow scoping secrets to an environment, preventing staging secrets from leaking into production jobs:

```yaml
# In the GitHub UI: Settings → Environments → production
# Add secrets: CLOUDFLARE_API_TOKEN (scoped prod token), D1_DATABASE_ID

jobs:
  deploy:
    environment: ${{ matrix.environment }}
    # Secrets resolved here are the ones set on the matching GitHub Environment
    steps:
      - name: Deploy
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken:  ${{ secrets.CLOUDFLARE_API_TOKEN }}   # Per-environment token
          command:   deploy --env ${{ matrix.environment }}
        env:
          D1_DATABASE_ID: ${{ secrets.D1_DATABASE_ID }}    # Per-environment D1
```

Each matrix leg resolves `secrets.*` from its own GitHub Environment, so `production` gets a read-write token with narrow Worker scopes while `preview` gets a separate token scoped to the preview namespace.

---

## Conditional Matrix Expansion Based on Changed Workers

Combine the selective-build pattern with matrix to only deploy Workers whose code changed:

```yaml
jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.set-matrix.outputs.matrix }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Detect changed workers
        id: set-matrix
        run: |
          CHANGED=$(git diff --name-only origin/main...HEAD \
            | grep '^apps/workers/' \
            | cut -d/ -f3 \
            | sort -u \
            | jq -R . | jq -sc .)

          if [[ "${CHANGED}" == "[]" ]]; then
            CHANGED='["api-gateway"]'   # fallback: always deploy gateway
          fi

          echo "matrix={\"worker\":${CHANGED},\"environment\":[\"preview\",\"staging\"]}" \
            >> "$GITHUB_OUTPUT"

  deploy:
    needs: detect
    if: ${{ needs.detect.outputs.matrix != '' }}
    strategy:
      matrix: ${{ fromJson(needs.detect.outputs.matrix) }}
    # ... deploy steps
```

---

## Wrangler Deploy Ordering via Job Dependencies

When Worker A (api-gateway) must deploy before Worker B (auth) — because B's service binding depends on A being live — express this with job dependencies rather than sequential matrix legs:

```yaml
jobs:
  deploy-gateway:
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: cloudflare/wrangler-action@v3
        with:
          command: deploy --env staging
          workingDirectory: apps/workers/api-gateway

  deploy-downstream:
    needs: deploy-gateway
    runs-on: ubuntu-latest
    environment: staging
    strategy:
      matrix:
        worker: [auth, payments, assets, cron]
    steps:
      - uses: cloudflare/wrangler-action@v3
        with:
          command: deploy --env staging
          workingDirectory: apps/workers/${{ matrix.worker }}
```

This creates a two-tier deploy: gateway first, then all downstream Workers in parallel.

---

## Deploy Summary Report

Aggregate matrix results into a workflow summary for visibility:

```yaml
      - name: Write deploy summary
        if: always()
        run: |
          echo "## Deploy: ${{ matrix.worker }} → ${{ matrix.environment }}" >> "$GITHUB_STEP_SUMMARY"
          echo "" >> "$GITHUB_STEP_SUMMARY"
          echo "- **Status**: ${{ job.status }}" >> "$GITHUB_STEP_SUMMARY"
          echo "- **Worker**: \`${{ matrix.worker }}\`" >> "$GITHUB_STEP_SUMMARY"
          echo "- **Environment**: \`${{ matrix.environment }}\`" >> "$GITHUB_STEP_SUMMARY"
          echo "- **Commit**: \`${{ github.sha }}\`" >> "$GITHUB_STEP_SUMMARY"
```

The GitHub Actions summary page then shows a per-leg status table after the workflow completes.

---

## Anti-patterns

- **Using `fail-fast: true` (the default)** — if one Worker's deploy fails, GitHub cancels in-flight legs, leaving the environment in a partial deploy state. Always set `fail-fast: false` for deploy matrices.
- **Sharing a single Cloudflare API token across all environments** — a compromised preview token can then deploy to production. Use environment-scoped tokens with the minimum required permissions (deploy to specific Worker name only).
- **Dynamic matrix from `fromJson` with unbounded size** — if the changed-workers detection script emits all workers on any root-file change, the matrix explodes to 15+ concurrent Wrangler deploys, hitting Cloudflare's API rate limits (429s).
- **Omitting `max-parallel`** — GitHub Actions runs all matrix legs concurrently by default; for large matrices this saturates Cloudflare's deploy API. Set `max-parallel: 4–6` for safety.

---

## Gotchas

- GitHub Environments with **required reviewers** block matrix legs until a human approves; this is intentional for production but can stall preview deploys if misconfigured. Use required reviewers only on the `production` environment.
- `matrix.include` adds new matrix legs (does not filter existing ones) and `matrix.exclude` removes them — the semantics are not symmetrical. Conditional production-only deploys require an `exclude` of the default environment list followed by explicit `include` rows.
- Wrangler reads `CLOUDFLARE_API_TOKEN` from the environment; the `apiToken` input in `cloudflare/wrangler-action` sets this env var. Both approaches work but do not mix them — the env var takes precedence over the input.
- Concurrency groups should be set at the environment level, not the job level, to prevent two PRs from simultaneously deploying to the same environment: `concurrency: group: deploy-${{ matrix.environment }}-${{ matrix.worker }}`.

---

## Verification

```bash
# 1. List matrix jobs from a workflow run
gh run view <run-id> --json jobs \
  --jq '.jobs[] | select(.name | test("Deploy")) | {name, conclusion}'

# 2. Confirm all environments were deployed
gh run view <run-id> --json jobs \
  --jq '[.jobs[].name] | sort'

# 3. Check Wrangler deployment versions per environment
wrangler deployments list --name example project-api-gateway --env staging
wrangler deployments list --name example project-api-gateway --env production
```

---

## Related

- `github-actions-wrangler-deploy-pipeline.md`
- `wrangler-environments-staging-production.md`
- `monorepo-wrangler-selective-deploy.md`
- `monorepo-deploy-order-workers-service-bindings.md`
- `github-actions-reusable-2026.md`
- `github-actions-concurrency-cancel-workers-deploy.md`
- `canary-deployment-strategy.md`

---

## Sources

- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/using-a-matrix-for-your-jobs
- https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment
- https://github.com/cloudflare/wrangler-action
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://developers.cloudflare.com/fundamentals/api/get-started/create-token/
