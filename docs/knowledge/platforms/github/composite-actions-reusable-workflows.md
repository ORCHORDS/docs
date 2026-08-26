# GitHub Actions: Composite Actions and Reusable Workflows

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your GitHub Actions workflows are copy-pasted across dozens of
repositories. A security update to a shared step (e.g., upgrading a
Node.js version or changing a Docker registry) requires editing every
repository's workflow file individually. Teams create slightly different
CI configurations, leading to inconsistent build, test, and deploy
processes. Platform engineering cannot enforce organization-wide CI/CD
standards.

## Context

GitHub Actions provides two mechanisms for sharing workflow logic:
composite actions (bundles of steps that run as a single step in a job)
and reusable workflows (complete workflow files that are called at the
job level). In 2026, the standard pattern is: platform teams publish
reusable workflows for organization-wide pipelines (build, test, deploy),
and individual teams create composite actions for team-specific step
bundles. The two mechanisms compose — a reusable workflow's jobs can use
composite actions inside their steps.

## Composite actions vs. reusable workflows

| Feature | Composite Action | Reusable Workflow |
|---|---|---|
| Scope | Steps within a job | One or more complete jobs |
| Called from | A step (`uses:`) | A job (`uses:`) |
| Secrets access | Inherited from caller | Must be passed explicitly |
| Multiple jobs | No | Yes |
| Matrix strategy | No (caller defines) | Yes (built-in) |
| Environment gates | No | Yes |
| Logging | Collapsed into one step | Each step logged separately |
| Location | Any directory with `action.yml` | `.github/workflows/` only |

### When to use each

```
Composite Action:
  → Bundling 2-5 related steps (setup, lint, format)
  → Shared utilities (install dependencies, configure cache)
  → Team-specific helpers

Reusable Workflow:
  → Organization-wide CI/CD pipelines
  → Multi-job workflows (build → test → deploy)
  → Workflows with environment protection rules
  → Standardized deploy pipelines
```

## Composite action

```yaml
# .github/actions/setup-node-pnpm/action.yml
name: 'Setup Node.js + pnpm'
description: 'Install Node.js and pnpm with caching'

inputs:
  node-version:
    description: 'Node.js version'
    required: false
    default: '22'

runs:
  using: 'composite'
  steps:
    - uses: actions/setup-node@v4
      with:
        node-version: ${{ inputs.node-version }}

    - uses: pnpm/action-setup@v4
      with:
        version: 9

    - name: Get pnpm store directory
      id: pnpm-cache
      shell: bash
      run: echo "dir=$(pnpm store path)" >> $GITHUB_OUTPUT

    - uses: actions/cache@v4
      with:
        path: ${{ steps.pnpm-cache.outputs.dir }}
        key: pnpm-${{ runner.os }}-${{ hashFiles('**/pnpm-lock.yaml') }}

    - name: Install dependencies
      shell: bash
      run: pnpm install --frozen-lockfile
```

### Using the composite action

```yaml
# .github/workflows/ci.yml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/setup-node-pnpm
        with:
          node-version: '22'
      - run: pnpm test
```

## Reusable workflow

```yaml
# .github/workflows/ci-pipeline.yml (in the shared repo)
name: CI Pipeline

on:
  workflow_call:
    inputs:
      node-version:
        type: string
        default: '22'
      run-e2e:
        type: boolean
        default: false
    secrets:
      NPM_TOKEN:
        required: false

jobs:
  lint-and-type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/setup-node-pnpm
        with:
          node-version: ${{ inputs.node-version }}
      - run: pnpm lint
      - run: pnpm type-check

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/setup-node-pnpm
      - run: pnpm test

  e2e:
    if: ${{ inputs.run-e2e }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/setup-node-pnpm
      - run: pnpm e2e
```

### Calling the reusable workflow

```yaml
# .github/workflows/ci.yml (in the consuming repo)
name: CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  ci:
    uses: my-org/shared-workflows/.github/workflows/ci-pipeline.yml@v1
    with:
      node-version: '22'
      run-e2e: true
    secrets:
      NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
```

## Versioning strategies

| Strategy | Example | Trade-off |
|---|---|---|
| **Tag (recommended)** | `uses: org/actions@v1` | Stable, controlled updates |
| **Branch** | `uses: org/actions@main` | Always latest, may break |
| **SHA** | `uses: org/actions@abc123` | Immutable, but hard to maintain |

### Semantic versioning with major tag

```bash
# Release a new version
git tag v1.2.0
git push origin v1.2.0

# Update the major tag to point to latest
git tag -f v1 v1.2.0
git push -f origin v1
```

Consumers using `@v1` automatically get minor and patch updates without
changing their workflows.

## Anti-patterns

- **Copy-pasting workflows** — duplicating workflow files across
  repositories. A security fix or tool upgrade must be applied to every
  copy. Use reusable workflows for organization-wide patterns.
- **One giant composite action** — bundling 20 steps into a single
  composite action makes it inflexible. Split into focused, composable
  actions (setup, lint, test, deploy).
- **Using `@main` for shared actions** — pointing to the `main` branch
  of a shared action repository means any push to main can break all
  consuming repositories. Use tagged versions.
- **Secrets in composite actions** — composite actions cannot declare
  secrets as inputs. If you need secrets, use a reusable workflow or
  pass secrets as environment variables from the caller.

## Gotchas

- **Nested reusable workflows** — reusable workflows can call other
  reusable workflows, but the maximum depth is 4 levels. Deeply nested
  workflows are hard to debug.
- **Matrix in reusable workflows** — the caller cannot pass a matrix
  to a reusable workflow. Define the matrix inside the reusable workflow
  or pass matrix values as comma-separated input strings and parse them.
- **Permissions inheritance** — reusable workflows inherit the caller's
  `GITHUB_TOKEN` permissions. If the reusable workflow needs additional
  permissions, declare them explicitly.
- **Composite action paths** — `uses: ./path` is relative to the
  repository root. When using composite actions from a monorepo, the
  path must be relative to the checkout root, not the package directory.

## Verification

- Organization-wide CI/CD pipeline uses reusable workflows from a
  shared repository.
- Shared actions and workflows are versioned with semantic tags.
- No copy-pasted workflow files across repositories.
- Platform team changes propagate to all consuming repos automatically.
- Composite actions complete in < 30 seconds for setup tasks.
- Reusable workflow documentation covers available inputs and secrets.

## Related

- `documentation/docs/policies/github/branch-protection-rules.md`
- `documentation/docs/policies/github/dependabot-configuration.md`
- `documentation/docs/policies/infra/ci-cd-pipeline-design.md`

## Source URLs (verified 2026-08-16)

- Reusable workflows guide — https://daminibansal.medium.com/reusable-github-actions-workflows-a-complete-guide-bb61283b9996
- Composite actions tutorial — https://oneuptime.com/blog/post/2026-01-27-github-actions-composite-actions/view
- Reusable workflows vs composite actions — https://tenki.cloud/blog/reusable-workflows-vs-composite-actions
- GitHub Actions comparison — https://nerdleveltech.com/github-actions-reusable-workflow-vs-composite-action
