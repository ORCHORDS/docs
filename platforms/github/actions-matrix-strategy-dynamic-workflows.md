# GitHub Actions — Matrix Strategy and Dynamic Workflows

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your CI pipeline runs tests sequentially across multiple environments
(Node 18, 20, 22; Ubuntu, macOS; PostgreSQL 15, 16) and takes 45+
minutes. Adding a new environment requires editing workflow YAML in
multiple places. Your matrix is hardcoded, so when a new version of a
dependency is released, you must manually update the workflow. Some
matrix combinations are invalid (e.g., ARM + Windows) but you cannot
exclude them cleanly. You want to parallelize across environments and
generate matrix combinations dynamically.

## Context

GitHub Actions' `strategy.matrix` allows defining multiple variable
combinations that generate parallel job runs. A 3×2 matrix (3 OS × 2
Node versions) creates 6 parallel jobs from a single job definition. In
2026, dynamic matrices — where combinations are generated at runtime
from script output, API calls, or file content — are the standard
pattern for large projects. Combined with `fromJSON()`, reusable
workflows, and conditional includes/excludes, matrix strategies enable
sophisticated CI configurations that adapt to the repository state.

## Static matrix

```yaml
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        node: [18, 20, 22]
      fail-fast: false  # Don't cancel other jobs on first failure
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node }}
      - run: npm ci
      - run: npm test
```

## Include and exclude

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
    node: [18, 20, 22]
    exclude:
      # Skip Node 18 on Windows (unsupported combination)
      - os: windows-latest
        node: 18
    include:
      # Add a specific combination with extra variables
      - os: ubuntu-latest
        node: 22
        coverage: true
        experimental: true
```

## Dynamic matrix with fromJSON

### From script output

```yaml
jobs:
  generate:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.set-matrix.outputs.matrix }}
    steps:
      - uses: actions/checkout@v4
      - id: set-matrix
        run: |
          # Generate matrix from package.json engines field
          MATRIX=$(node -e "
            const pkg = require('./package.json');
            const versions = pkg.engines.node
              .split('||')
              .map(v => v.trim().replace('>=', '').replace('.x', ''));
            console.log(JSON.stringify({
              node: versions,
              os: ['ubuntu-latest', 'macos-latest']
            }));
          ")
          echo "matrix=$MATRIX" >> "$GITHUB_OUTPUT"

  test:
    needs: generate
    strategy:
      matrix: ${{ fromJSON(needs.generate.outputs.matrix) }}
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node }}
      - run: npm ci && npm test
```

### From changed files (monorepo)

```yaml
jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      packages: ${{ steps.changes.outputs.packages }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2
      - id: changes
        run: |
          CHANGED=$(git diff --name-only HEAD~1 HEAD \
            | grep '^packages/' \
            | cut -d'/' -f2 \
            | sort -u \
            | jq -R -s -c 'split("\n") | map(select(. != ""))')
          echo "packages=$CHANGED" >> "$GITHUB_OUTPUT"

  test:
    needs: detect-changes
    if: needs.detect-changes.outputs.packages != '[]'
    strategy:
      matrix:
        package: ${{ fromJSON(needs.detect-changes.outputs.packages) }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cd packages/${{ matrix.package }} && npm ci && npm test
```

### From API response

```yaml
jobs:
  get-environments:
    runs-on: ubuntu-latest
    outputs:
      envs: ${{ steps.fetch.outputs.envs }}
    steps:
      - id: fetch
        run: |
          ENVS=$(curl -s https://api.example.com/environments \
            | jq -c '[.[] | select(.active) | .name]')
          echo "envs=$ENVS" >> "$GITHUB_OUTPUT"

  deploy:
    needs: get-environments
    strategy:
      matrix:
        environment: ${{ fromJSON(needs.get-environments.outputs.envs) }}
      max-parallel: 2
    runs-on: ubuntu-latest
    environment: ${{ matrix.environment }}
    steps:
      - run: echo "Deploying to ${{ matrix.environment }}"
```

## Matrix with max-parallel

```yaml
strategy:
  matrix:
    service: [api, web, worker, scheduler, mailer, analytics]
  max-parallel: 3  # Run at most 3 jobs concurrently
  fail-fast: false
```

## Matrix with reusable workflows

```yaml
# .github/workflows/test-package.yml (reusable)
on:
  workflow_call:
    inputs:
      package:
        required: true
        type: string
      node-version:
        required: true
        type: string

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ inputs.node-version }}
      - run: cd packages/${{ inputs.package }} && npm ci && npm test
```

```yaml
# Caller workflow
jobs:
  test:
    strategy:
      matrix:
        package: [core, api, web]
        node: ['20', '22']
    uses: ./.github/workflows/test-package.yml
    with:
      package: ${{ matrix.package }}
      node-version: ${{ matrix.node }}
```

## Anti-patterns

- **Huge matrices without fail-fast: false** — a 5×3×2 matrix creates
  30 jobs. With `fail-fast: true` (default), one failure cancels all
  29 other jobs, wasting the work already done. Set `fail-fast: false`
  for matrices where you want full coverage results.
- **Hardcoded versions in large matrices** — manually listing every
  version in the matrix YAML. Use dynamic generation from
  `package.json`, `.tool-versions`, or API calls so the matrix stays
  current without manual edits.
- **No max-parallel on expensive jobs** — running 20 parallel
  deployment jobs overwhelms infrastructure. Use `max-parallel` for
  resource-intensive operations like deployments and load tests.
- **Matrix for sequential dependencies** — using a matrix for steps
  that must run in order (build → test → deploy). Matrix jobs run in
  parallel; use `needs` for sequential dependencies.

## Gotchas

- **Output size limits** — GitHub Actions outputs are limited to
  1 MB. If your dynamic matrix generates too many combinations, the
  output exceeds the limit and the workflow fails. Filter or paginate
  large matrices.
- **fromJSON type coercion** — `fromJSON` parses strings. If your
  matrix values are numbers (e.g., Node versions `18, 20`), ensure
  they are output as JSON numbers, not strings, to avoid type
  mismatches in `setup-node`.
- **Empty matrix** — if a dynamic matrix evaluates to an empty array,
  the job fails. Guard with an `if` condition:
  `if: fromJSON(needs.gen.outputs.matrix).length > 0`.
- **Matrix job naming** — each matrix job gets a name like
  `test (ubuntu-latest, 20)`. Long matrix variable names create
  unwieldy job names. Use short, descriptive matrix keys.

## Verification

- CI matrices cover all supported environments (OS, runtime versions).
- Dynamic matrices update automatically when dependencies change.
- fail-fast is disabled for full coverage reports.
- max-parallel limits resource-intensive parallel jobs.
- Empty matrix edge case is handled with conditional guards.
- Matrix generation is tested in a separate workflow.

## Related

- `documentation/categories/github/composite-actions-reusable-workflows.md`
- `documentation/categories/deploy/gitops-argocd-flux-patterns.md`
- `documentation/categories/testing/contract-testing-pact-patterns.md`

## Source URLs (verified 2026-08-16)

- GitHub Actions Matrix Strategy Tutorial and Best Practices — https://octopus.com/devops/github-actions/github-actions-matrix/
- Dynamic GitHub Actions Matrix: Enhance Engineering Performance — https://devactivity.com/posts/productivity-tips/unlocking-dynamic-matrix-builds-boost-engineering-performance-in-github-actions/
- The Matrix Strategy in GitHub Actions — https://runs-on.com/github-actions/the-matrix-strategy/
- GitHub Actions: Dynamically Set Strategy Matrix Using Script Output — https://www.tutorialpedia.org/blog/github-actions-how-use-strategy-matrix-with-script/
