# github-actions-reusable-workflows

**Issue:** GitHub Actions — reusable workflows, matrices
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have 10 repos. Each has a slightly different CI
config. The lint command is different in 3. The test
command is duplicated 8 times. A version update means
10 PRs.

## Root cause
**Without reusable workflows, CI is duplicated.** Use
reusable workflows.

**Source:** GitHub docs:
https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows

## The "reusable workflow" concept

A reusable workflow is a workflow called by other
workflows:
- **Centralized:** One definition
- **Inputs:** Parameters
- **Outputs:** Return values
- **Nesting:** Up to 10 levels

The workflow is reused.

## The "create" pattern

For a reusable workflow:
```yaml
# .github/workflows/build-and-test.yml
name: Build and Test
on:
  workflow_call:
    inputs:
      node-version:
        required: true
        type: string
    secrets:
      NPM_TOKEN:
        required: true

jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ inputs.node-version }}
      - run: npm ci
        env:
          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
      - run: npm test
```

The workflow is reusable.

## The "call" pattern

For calling:
```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  call-build-test:
    uses: ./.github/workflows/build-and-test.yml
    with:
      node-version: '20'
    secrets:
      NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
```

The workflow is called.

## The "matrix" pattern

For matrix in the caller:
```yaml
jobs:
  deploy:
    strategy:
      matrix:
        target: [dev, stage, prod]
    uses: octocat/octo-repo/.github/workflows/deploy.yml@main
    with:
      target: ${{ matrix.target }}
```

The matrix is in the caller.

**Caveat:** As of 2026, GitHub still doesn't support
passing a matrix as an input. Define matrix inside the
reusable workflow.

## The "inputs" pattern

For inputs:
```yaml
# Reusable workflow
on:
  workflow_call:
    inputs:
      config-path:
        required: true
        type: string
      enable-cache:
        required: false
        type: boolean
        default: 'true'
```

The inputs are typed.

## The "secrets" pattern

For secrets:
```yaml
# Reusable workflow
on:
  workflow_call:
    secrets:
      personal_access_token:
        required: true
```

```yaml
# Caller
jobs:
  call:
    uses: ./.github/workflows/deploy.yml
    secrets:
      personal_access_token: ${{ secrets.PAT }}
```

The secrets are explicit.

**Caveat:** Secrets are NOT auto-forwarded.

## The "secrets: inherit" pattern

For inherited secrets:
```yaml
# Caller
jobs:
  call:
    uses: ./.github/workflows/deploy.yml
    secrets: inherit
```

All secrets are passed.

## The "outputs" pattern

For outputs:
```yaml
# Reusable workflow
jobs:
  build:
    outputs:
      artifact-url: ${{ steps.upload.outputs.url }}
    steps:
      - id: upload
        run: echo "url=..." >> $GITHUB_OUTPUT
```

```yaml
# Caller
jobs:
  call:
    uses: ./.github/workflows/deploy.yml
  use:
    needs: call
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ needs.call.outputs.artifact-url }}
```

The outputs are passed.

**Note:** With matrix, output is the last completing job's
output (or second-to-last if last is empty).

## The "nesting" pattern

For nesting:
- **Max:** 10 levels
- **Use case:** Modular CI

```yaml
# Top-level
jobs:
  call-build:
    uses: ./.github/workflows/build.yml
```

```yaml
# build.yml
jobs:
  call-test:
    uses: ./.github/workflows/test.yml
```

The depth is tracked.

## The "version pinning" pattern

For production, pin to a commit SHA:
```yaml
jobs:
  call:
    uses: octocat/repo/.github/workflows/ci.yml@a1b2c3d4
```

The version is fixed.

**Why:** Branch refs can change; SHAs are immutable.

## The "vs composite action" choice

| Use case | Use |
|---|---|
| **Multi-job / matrix** | Reusable workflow |
| **Single-job steps** | Composite action |
| **Cross-language** | Composite action |
| **Cross-repo** | Reusable workflow |

For most use cases, **reusable workflow** is more
powerful.

## The "matrix optimization" pattern

For optimization:
- **fail-fast: false:** See all failures
- **max-parallel:** Limit concurrency
- **include:** Add specific cases
- **exclude:** Skip invalid combinations

```yaml
strategy:
  fail-fast: false
  max-parallel: 6
  matrix:
    os: [ubuntu-22.04, ubuntu-24.04, macos-14]
    node-version: [20, 22]
    include:
      - os: ubuntu-24.04
        node-version: 22
        coverage: true
    exclude:
      - os: macos-14
        node-version: 20
```

The matrix is optimized.

## The "secret forwarding" pattern

For secret forwarding, EXPLICIT:
- **Don't rely on auto-forward**
- **List each secret**
- **Use `secrets: inherit` if all needed**

The secrets are explicit.

## The "composite action" pattern

For composite actions:
```yaml
# .github/actions/setup-node-pnpm/action.yml
name: 'Setup Node + pnpm'
description: 'Setup Node.js with pnpm'
runs:
  using: 'composite'
  steps:
    - uses: actions/setup-node@v4
      with:
        node-version: '20'
    - run: npm install -g pnpm
      shell: bash
```

```yaml
# Caller
- uses: ./.github/actions/setup-node-pnpm
```

The action is reusable.

## The "larger runners" pattern

For larger runners:
- **GitHub-hosted:** 4-core, 8-core, 16-core, 64-core
- **Self-hosted:** Custom

```yaml
jobs:
  build:
    runs-on: ubuntu-latest-4-core
```

The runner is bigger.

## The "reusable workflow anti-pattern" anti-patterns

### 1. Branch ref in production
- **Issue:** Can change
- **Fix:** Pin to SHA

### 2. No secret forwarding
- **Issue:** Auth fails
- **Fix:** Explicit secrets

### 3. Matrix in caller (not reusable)
- **Issue:** Can't share matrix
- **Fix:** Move matrix to reusable

### 4. Too many levels
- **Issue:** Hard to debug
- **Fix:** Max 4-5 levels

## Verification
- **Test:** Workflow is called
- **Test:** Inputs are passed
- **Test:** Secrets are passed
- **Test:** Outputs are returned
- **Live:** Workflow health
- **Audit:** Quarterly review

## Gotchas
- **The "branch ref" anti-pattern.** Pin to SHA.
- **The "no secret forwarding" anti-pattern.** Explicit.
- **The "matrix in caller" anti-pattern.** In reusable.

## Related
- `github/dependabot-config.md`
- `github/pr-template-and-issue-templates.md`
- `github/pat-self-merge-workaround.md`
- `infra/github-self-hosted-runners.md`
- GitHub docs: https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows
- Sachith guide: https://www.sachith.co.uk/github-actions-reusable-workflows-matrices-from-zero-to-production-practical-guide-may-7-2026/
