# Building a GitHub Actions Composite Action for Wrangler Operations

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Every repository that deploys a Cloudflare Worker repeats the same three-step boilerplate: install Wrangler at a pinned version, authenticate with a CF API token, then run a Wrangler command. A composite action encapsulates those steps behind a single `uses:` line and makes the version pin and auth logic a single place to update.

## Context

GitHub composite actions (`runs.using: composite`) bundle multiple shell steps and other action references into one reusable action defined in `action.yml`. Unlike reusable workflows they can be called as a step rather than a job, so they compose cleanly with other steps in a job. Publishing the action to a private GitHub Packages registry (or a dedicated `actions` repository) makes it available across the organisation.

## Composite Action Definition

Create a repository `example-org/example-repo` with the following layout:

```
actions/
  wrangler/
    action.yml
    README.md
```

```yaml
# example-org/example-repo/wrangler/action.yml
name: "Wrangler"
description: "Install Wrangler, authenticate with Cloudflare, and run a wrangler command"
author: "example.com"

inputs:
  wrangler_version:
    description: "Wrangler CLI version to install (npm semver)"
    required: false
    default: "3.57.0"
  command:
    description: "Wrangler sub-command and flags, e.g. 'deploy --env production'"
    required: true
  working_directory:
    description: "Directory containing wrangler.toml"
    required: false
    default: "."
  node_version:
    description: "Node.js version"
    required: false
    default: "20"

runs:
  using: composite
  steps:
    - name: Setup Node.js
      uses: actions/setup-node@v4
      with:
        node-version: ${{ inputs.node_version }}
        cache: npm

    - name: Install Wrangler
      shell: bash
      run: npm install -g wrangler@${{ inputs.wrangler_version }}

    - name: Authenticate with Cloudflare
      shell: bash
      env:
        CLOUDFLARE_API_TOKEN: ${{ env.CF_API_TOKEN }}
        CLOUDFLARE_ACCOUNT_ID: ${{ env.CF_ACCOUNT_ID }}
      run: |
        if [ -z "$CLOUDFLARE_API_TOKEN" ]; then
          echo "::error::CF_API_TOKEN environment variable is not set"
          exit 1
        fi
        wrangler whoami

    - name: Run wrangler ${{ inputs.command }}
      shell: bash
      working-directory: ${{ inputs.working_directory }}
      env:
        CLOUDFLARE_API_TOKEN: ${{ env.CF_API_TOKEN }}
        CLOUDFLARE_ACCOUNT_ID: ${{ env.CF_ACCOUNT_ID }}
      run: wrangler ${{ inputs.command }}
```

## Using the Composite Action in a Workflow

```yaml
# .github/workflows/deploy.yml  (in any repository)
name: Deploy Worker

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-24.04
    environment: production

    steps:
      - uses: actions/checkout@v4

      - name: Install npm dependencies
        run: npm ci

      - name: Deploy to production
        uses: example-org/example-repo/wrangler@v1
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN_PROD }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        with:
          command: "deploy --env production"
          working_directory: packages/my-worker

      - name: Run Wrangler tail (smoke test)
        uses: example-org/example-repo/wrangler@v1
        env:
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN_PROD }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        with:
          command: "deployments list --env production"
          working_directory: packages/my-worker
```

## Versioning and Publishing to GitHub Packages

```bash
# In the example-org/example-repo repository:

# Tag a release
git tag -a v1.0.0 -m "Initial composite wrangler action"
git push origin v1.0.0

# Create a major version tag that floats to the latest patch
git tag -fa v1 -m "Update v1 to v1.0.0"
git push origin v1 --force
```

For organisations that want immutable action references, pin callers to the full semver tag (`@v1.0.0`) and update them via Dependabot:

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    groups:
      orchords-actions:
        patterns:
          - "example-org/example-repo*"
```

## Extending the Action: Publishing to Preview Environments

```yaml
# action.yml addition — optional input for preview deployments
inputs:
  preview_name:
    description: "If set, deploy to a Workers preview branch with this name"
    required: false
    default: ""

# Additional step in runs.steps:
    - name: Deploy preview (if preview_name set)
      if: ${{ inputs.preview_name != '' }}
      shell: bash
      working-directory: ${{ inputs.working_directory }}
      env:
        CLOUDFLARE_API_TOKEN: ${{ env.CF_API_TOKEN }}
        CLOUDFLARE_ACCOUNT_ID: ${{ env.CF_ACCOUNT_ID }}
      run: |
        wrangler versions upload \
          --message "PR preview: ${{ inputs.preview_name }}"
```

## Anti-patterns

- Hardcoding the CF API token inside `action.yml` — tokens must always come from the calling workflow's secrets via environment variables.
- Using `runs.using: node20` for a script that only calls the CLI — composite is simpler and has no compilation step.
- Omitting `wrangler whoami` in the auth step — silent auth failures surface only when the actual deploy fails, making debugging harder.
- Referencing the action with `@main` in production workflows — a commit to `main` of the actions repo could break all callers immediately.

## Gotchas

- Composite action steps do not automatically inherit the calling job's `env:` block; you must pass secrets explicitly via `env:` on the `uses:` step and reference them as `${{ env.VAR }}` inside the action (not `${{ secrets.VAR }}`).
- GitHub does not support `secrets:` inputs in composite actions (only in reusable workflows). Pass secrets through environment variables.
- The `working-directory` key inside a composite action step is relative to the **repository root of the calling workflow**, not the action repository.
- Composite actions cannot define `permissions:` — set those in the calling job.

## Verification

```bash
# List all tags in the actions repo
gh release list --repo example-org/example-repo

# Confirm the action is resolvable
gh api repos/example-org/example-repo/contents/wrangler/action.yml \
  --jq '.content' | base64 -d | head -10

# Run the workflow locally with act
act push --secret CF_API_TOKEN=test --secret CF_ACCOUNT_ID=abc123
```

## Related

- `github-actions-reusable-workflows-workers-deploy.md`
- `github-environments-cloudflare-deployment-protection.md`

## Sources

- https://docs.github.com/en/actions/sharing-automations/creating-actions/creating-a-composite-action
- https://developers.cloudflare.com/workers/wrangler/
- https://docs.github.com/en/code-security/dependabot/working-with-dependabot/keeping-your-actions-up-to-date-with-dependabot
