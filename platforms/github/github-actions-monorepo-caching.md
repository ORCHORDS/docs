# github-actions-monorepo-caching

**Issue:** GitHub Actions — caching, OIDC, monorepo
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your CI is slow. 30+ minutes per run. You store
50 static secrets. Each monorepo package rebuilds
independently. You wish you had better CI.

## Root cause
**No caching, static secrets, no change detection.** Fix.

**Source:** Hossain + 7tech + sachith 2026.

## The "4 pillars" pattern

For CI:
- **Reusable workflows:** Standardize
- **Change-aware:** Only impacted
- **Stable caching:** 60-80% speedup
- **OIDC:** No static secrets

The 4 are the pillars.

## The "OIDC" pattern

For secrets:
- **Token:** Short-lived JWT
- **Scope:** Per repo + branch
- **Rotation:** Auto
- **No static:** AWS / GCP creds
- **Use:** Cloud deploys

The OIDC is the new way.

## The "OIDC for AWS" pattern

For AWS:
```yaml
permissions:
  id-token: write
  contents: read
steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: arn:aws:iam::123:role/GHA
      aws-region: us-east-1
```

The AWS is OIDC.

## The "OIDC for GCP" pattern

For GCP:
```yaml
permissions:
  id-token: write
steps:
  - uses: google-github-actions/auth@v2
    with:
      workload_identity_provider: projects/123/locations/global/workloadIdentityPools/...
      service_account: gha@project.iam.gserviceaccount.com
```

The GCP is OIDC.

## The "cache key" pattern

For key:
```yaml
- uses: actions/cache@v4
  with:
    path: ~/.npm
    key: npm-${{ runner.os }}-${{ hashFiles('**/package-lock.json') }}
    restore-keys: |
      npm-${{ runner.os }}-
```

The key is hashed.

## The "cache size" pattern

For limits:
- **10 GB:** Per repo
- **7 days:** Eviction
- **Multiple keys:** Restore fallbacks
- **No cache:** 7 days unused = evict

The size is capped.

## The "matrix strategy" pattern

For matrix:
```yaml
strategy:
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
    node: [20, 22]
steps:
  - uses: actions/setup-node@v4
    with:
      node-version: ${{ matrix.node }}
```

The matrix is parallel.

## The "fail-fast" pattern

For matrix:
```yaml
strategy:
  matrix:
    os: [ubuntu, macos, windows]
  fail-fast: false  # Run all even if one fails
```

The fail-fast is per need.

## The "monorepo change detection" pattern

For monorepo:
```yaml
jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.mk.outputs.matrix }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - id: changed
        uses: tj-actions/changed-files@v46
        with:
          json: true
      - id: mk
        run: |
          node .github/scripts/targets-from-changes.mjs \
            '${{ steps.changed.outputs.all_changed_files }}' > matrix.json
          echo "matrix=$(cat matrix.json)" >> $GITHUB_OUTPUT
```

The detection is per PR.

## The "path filter" pattern

For paths:
```yaml
on:
  push:
    paths:
      - 'apps/web/**'
      - 'packages/shared/**'
      - '!.github/**'
```

The filter is per file.

## The "concurrency" pattern

For cancel:
```yaml
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```

The concurrency is auto.

## The "SHA pinning" pattern

For security:
```yaml
uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11  # v4.1.1
```

The SHA is pinned.

## The "permissions" pattern

For minimum:
```yaml
permissions:
  contents: read
  pull-requests: write
  # No other permissions
```

The permissions are minimal.

## The "environment protection" pattern

For prod:
```yaml
jobs:
  deploy:
    environment:
      name: production
      url: https://prod.example.com
    runs-on: ubuntu-latest
```

The env is gated.

## The "timeout" pattern

For runaway:
```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 20
```

The timeout is set.

## The "matrix input limitation" pattern

For reusable:
- **Limit:** Matrices not passed as inputs
- **Workaround:** Declare in reusable
- **Result:** Caller passes params

The matrix is in the called.

## The "secret forwarding" pattern

For reusable:
```yaml
jobs:
  call:
    uses: ./.github/workflows/build.yml
    with:
      node: 22
    secrets:
      NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
```

The secret is forwarded.

## The "secrets inherit" pattern

For pass all:
```yaml
uses: ./.github/workflows/build.yml
secrets: inherit
```

The secrets are inherited.

## The "nesting limit" pattern

For depth:
- **Max:** 3 levels
- **Caller → reusable → reusable → ❌**
- **Why:** Prevent unbounded
- **Fix:** Flatten

The depth is capped.

## The "no SHA pinning" anti-pattern

For unpinned:
- **Issue:** Supply chain
- **Fix:** Pin to SHA

The SHA is set.

## The "static secrets" anti-pattern

For static:
- **Issue:** Long-lived leak
- **Fix:** OIDC

The OIDC replaces.

## The "no caching" anti-pattern

For no cache:
- **Issue:** Slow CI
- **Fix:** Cache lockfiles

The cache is used.

## The "no matrix" anti-pattern

For no matrix:
- **Issue:** Sequential
- **Fix:** Parallel matrix

The matrix is parallel.

## The "no change detection" anti-pattern

For monorepo:
- **Issue:** All rebuilds
- **Fix:** Path filter + matrix

The detection is per PR.

## The "fail-fast true" anti-pattern

For fail-fast:
- **Issue:** Cancel on first fail
- **Fix:** `fail-fast: false`

The fast is per need.

## The "no concurrency" anti-pattern

For no cancel:
- **Issue:** Stale runs
- **Fix:** `cancel-in-progress: true`

The cancel is enabled.

## The "max permissions" anti-pattern

For wide:
- **Issue:** Token can do too much
- **Fix:** Minimal permissions

The perm is minimal.

## The "matrix inputs" anti-pattern

For passing matrix:
- **Issue:** Not supported
- **Fix:** Declare in reusable

The matrix is internal.

## The "Org secret leak" anti-pattern

For org secrets:
- **Issue:** In PR forks
- **Fix:** Environment-scoped

The env is scoped.

## The "CI checklist" pattern

For checklist:
- [ ] OIDC for cloud
- [ ] SHA pinned
- [ ] Minimal permissions
- [ ] Concurrency
- [ ] Cancel stale
- [ ] Path filter
- [ ] Change detection
- [ ] Matrix parallel
- [ ] Cache per key
- [ ] Timeout set
- [ ] Env scoped

The checklist is 11.

## Verification
- **Test:** CI < 10 min
- **Test:** Cache hit rate > 80%
- **Test:** Only impacted built
- **Test:** OIDC no static
- **Audit:** Quarterly

## Gotchas
- **The "no SHA" anti-pattern.** Pin.
- **The "static secrets" anti-pattern.** OIDC.
- **The "no caching" anti-pattern.** Use cache.

## Related
- `github/reusable-workflows-vs-composite.md`
- `github/branch-protection-and-codeowners.md`
- `github/dependabot-config.md`
- `github/pat-self-merge-workaround.md`
- `infra/arc-github-runners-k8s.md`
- `infra/monorepo-2026.md`
- `deploy/canary-deployments.md`
- Hossain: https://mdsanwarhossain.me/blog-github-actions-advanced-reusable-workflows.html
- 7tech: https://www.7tech.co.in/github-actions-in-2026-fast-secure-monorepo-ci-with-reusable-workflows-oidc-and-smart-caching/
- sachith: https://www.sachith.co.uk/github-actions-reusable-workflows-matrices-from-zero-to-production-practical-guide-may-7-2026/
