# Reusable GitHub Actions Workflows for Cloudflare Workers Deployments

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You maintain multiple Cloudflare Workers packages in a monorepo. Each package has its own deploy job, and updating the Wrangler version or adding a new deployment step requires touching every workflow file. A single reusable workflow definition lets you propagate changes in one place.

## Context

GitHub Actions supports `workflow_call` as a trigger, turning any workflow file into a callable component. The calling workflow passes typed inputs and inherits secrets, while the reusable workflow encapsulates all deployment logic. This pattern is ideal for monorepos with many Workers where consistency and DRY principles matter.

## Reusable Workflow Definition

Create `.github/workflows/deploy-worker.yml` in the root of your repository:

```yaml
# .github/workflows/deploy-worker.yml
# Reusable workflow — called by per-package workflows via `uses:`
name: Deploy Cloudflare Worker (reusable)

on:
  workflow_call:
    inputs:
      worker_name:
        description: "The Wrangler worker name (matches wrangler.toml name field)"
        required: true
        type: string
      environment:
        description: "Target environment: staging | production"
        required: true
        type: string
        default: staging
      wrangler_version:
        description: "Wrangler CLI version to install"
        required: false
        type: string
        default: "3.57.0"
      working_directory:
        description: "Path to the worker package inside the monorepo"
        required: false
        type: string
        default: "."
    secrets:
      CF_API_TOKEN:
        required: true
      CF_ACCOUNT_ID:
        required: true

jobs:
  deploy:
    name: Deploy ${{ inputs.worker_name }} → ${{ inputs.environment }}
    runs-on: ubuntu-24.04
    environment: ${{ inputs.environment }}

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - name: Install dependencies
        working-directory: ${{ inputs.working_directory }}
        run: npm ci

      - name: Install Wrangler
        run: npm install -g wrangler@${{ inputs.wrangler_version }}

      - name: Deploy Worker
        working-directory: ${{ inputs.working_directory }}
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          wrangler deploy \
            --name ${{ inputs.worker_name }} \
            --env ${{ inputs.environment }}

      - name: Verify deployment
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          wrangler deployments list \
            --name ${{ inputs.worker_name }} \
            --env ${{ inputs.environment }} \
            | head -5
```

## Calling the Reusable Workflow from a Package

Each Worker package maintains a thin caller workflow:

```yaml
# packages/api-gateway/.github/workflows/deploy.yml
# OR, for monorepos, store at root: .github/workflows/deploy-api-gateway.yml
name: Deploy api-gateway

on:
  push:
    branches: [main]
    paths:
      - "packages/api-gateway/**"
      - ".github/workflows/deploy-worker.yml" # also re-deploy on reusable change

jobs:
  deploy-staging:
    uses: ./.github/workflows/deploy-worker.yml
    with:
      worker_name: api-gateway
      environment: staging
      working_directory: packages/api-gateway
    secrets: inherit

  deploy-production:
    needs: deploy-staging
    uses: ./.github/workflows/deploy-worker.yml
    with:
      worker_name: api-gateway
      environment: production
      working_directory: packages/api-gateway
    secrets: inherit
```

## Propagating Changes Across All Workers

When you update `deploy-worker.yml` — for example, bumping the default `wrangler_version` or adding an OTEL tracing step — every caller workflow inherits the change on its next run. No PRs need to touch individual package workflows.

To force all workers to redeploy after a reusable workflow change, add a manual trigger or use a top-level dispatch workflow:

```yaml
# .github/workflows/redeploy-all.yml
name: Redeploy all Workers

on:
  workflow_dispatch:
    inputs:
      environment:
        type: choice
        options: [staging, production]
        default: staging

jobs:
  api-gateway:
    uses: ./.github/workflows/deploy-worker.yml
    with:
      worker_name: api-gateway
      environment: ${{ inputs.environment }}
      working_directory: packages/api-gateway
    secrets: inherit

  auth-service:
    uses: ./.github/workflows/deploy-worker.yml
    with:
      worker_name: auth-service
      environment: ${{ inputs.environment }}
      working_directory: packages/auth-service
    secrets: inherit
```

## Versioning the Reusable Workflow

For cross-repository reuse (not just same-repo), push the reusable workflow to a dedicated `actions` repository and reference it with a tag:

```yaml
jobs:
  deploy:
    uses: example-org/example-repo/.github/workflows/deploy-worker.yml@v2
    with:
      worker_name: my-worker
      environment: production
    secrets: inherit
```

Tag releases with semver and pin callers to major version tags (`@v2`) so breaking changes are opt-in.

## Anti-patterns

- Duplicating the full deploy job in every package workflow — a wrangler version bump requires N PRs.
- Putting environment-specific secrets inside `inputs` (they leak into logs); always pass them via `secrets`.
- Using `secrets: inherit` without understanding which secrets are available in the calling workflow's scope — verify the GitHub environment grants access to the needed secrets.
- Referencing the reusable workflow by a mutable branch name (`@main`) in production callers — pin to a tag for stability.

## Gotchas

- `workflow_call` cannot be combined with other triggers in the same job — the reusable workflow file must be dedicated to `on: workflow_call`.
- Concurrency groups defined in the reusable workflow are evaluated independently from the caller; set `concurrency` in the caller if you need deploy serialisation per environment.
- GitHub limits reusable workflow nesting to 4 levels deep.
- The `paths` filter in the caller workflow does not apply when the workflow is triggered via `workflow_call` from another workflow.

## Verification

```bash
# List recent workflow runs for the reusable workflow
gh run list --workflow deploy-worker.yml --repo example-org/example-repo

# Watch a specific run
gh run watch <run-id>

# Confirm the worker is live
curl -s https://api-gateway.orchords.workers.dev/health | jq .status
```

## Related

- `github-environments-cloudflare-deployment-protection.md`
- `github-actions-composite-action-wrangler.md`
- `github-merge-queue-workers-ci-validation.md`

## Sources

- https://docs.github.com/en/actions/sharing-automations/reusing-workflows
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#workflow_call
