# github-actions-composite-actions

**Issue:** Creating reusable local action steps with composite actions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The same sequence of steps (setup Node, restore cache, install deps) is copy-pasted across dozens of workflows. Reusable workflows are too heavy for step-level reuse; composite actions are the right tool.

## Pattern / Solution
A composite action lives in `.github/actions/<name>/action.yml` and can be called like any marketplace action. It supports inputs, outputs, and runs shell steps.

**`.github/actions/setup-node-project/action.yml`:**
```yaml
name: Setup Node Project
description: Install deps with cache restore

inputs:
  node-version:
    description: Node.js version
    required: false
    default: '20'
  working-directory:
    description: Directory containing package.json
    required: false
    default: '.'

outputs:
  cache-hit:
    description: Whether the cache was restored
    value: ${{ steps.cache.outputs.cache-hit }}

runs:
  using: composite
  steps:
    - uses: actions/setup-node@v4
      with:
        node-version: ${{ inputs.node-version }}

    - name: Restore cache
      id: cache
      uses: actions/cache@v4
      with:
        path: ${{ inputs.working-directory }}/node_modules
        key: node-${{ inputs.node-version }}-${{ hashFiles(format('{0}/package-lock.json', inputs.working-directory)) }}

    - name: Install dependencies
      if: steps.cache.outputs.cache-hit != 'true'
      shell: bash
      working-directory: ${{ inputs.working-directory }}
      run: npm ci
```

**Calling the composite action from a workflow:**
```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: ./.github/actions/setup-node-project
        with:
          node-version: '22'
          working-directory: apps/api

      - run: npm test
        working-directory: apps/api
```

**Composite action with post step (cleanup):**
```yaml
runs:
  using: composite
  steps:
    - name: Main work
      shell: bash
      run: echo "doing work"
    # No native post: support — use always() in callers instead
```

## Gotchas
- Every `run:` step in a composite action **must** declare `shell:` explicitly — there is no default shell inheritance from the caller
- Composite actions cannot use `secrets:` inputs directly; pass secrets as regular inputs from the calling workflow
- `uses:` references inside a composite action must use full `owner/repo@ref` — relative paths only work for the top-level `action.yml`
- Composite actions don't support `services:` or `container:` — use reusable workflows for those
- Outputs from composite actions require the `value:` field pointing to a step expression; the step `id` must be set

## Related
- `reusable-workflows-vs-composite.md`
- `github-actions-reusable-workflows.md`
- `github-actions-monorepo-caching.md`
