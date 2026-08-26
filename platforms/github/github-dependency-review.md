# github-dependency-review

**Issue:** Blocking PRs that introduce vulnerable or license-incompatible dependencies
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A PR bumps a transitive dependency to a version with a known CVE or introduces a GPL-licensed package into a proprietary codebase. Dependency review catches this at PR time before it reaches main.

## Pattern / Solution
`actions/dependency-review-action` compares the dependency manifest between the PR base and head and fails the check if new vulnerable or disallowed dependencies are added.

**Basic dependency review workflow:**
```yaml
name: Dependency Review

on:
  pull_request:
    paths:
      - 'package-lock.json'
      - 'yarn.lock'
      - 'pnpm-lock.yaml'
      - 'Gemfile.lock'
      - 'requirements*.txt'
      - 'go.sum'
      - 'Cargo.lock'

permissions:
  contents: read
  pull-requests: write    # to post a comment summary

jobs:
  dependency-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/dependency-review-action@v4
        with:
          fail-on-severity: moderate    # low | moderate | high | critical
          deny-licenses: GPL-2.0, GPL-3.0, AGPL-3.0
          comment-summary-in-pr: always
```

**Allow specific advisories (known false positives):**
```yaml
          allow-ghsas: GHSA-xxxx-xxxx-xxxx, GHSA-yyyy-yyyy-yyyy
```

**Fail only on direct dependencies:**
```yaml
          warn-only: true              # report but don't fail
          fail-on-scopes: runtime     # runtime | development | unknown
```

**Custom config file:**
```yaml
# .github/dependency-review-config.yml
fail-on-severity: high
deny-licenses:
  - GPL-2.0-only
  - GPL-3.0-only
allow-dependencies-licenses:
  - pkg:npm/some-gpl-exception@1.0.0
comment-summary-in-pr: on-failure
```

```yaml
      - uses: actions/dependency-review-action@v4
        with:
          config-file: .github/dependency-review-config.yml
```

## Gotchas
- Dependency review requires the dependency graph to be enabled — check Settings → Security → Dependency graph
- The action checks newly added vulnerabilities in the PR diff only — existing vulnerabilities in the base branch are not reported (use Dependabot alerts for that)
- License detection is best-effort and based on SPDX identifiers in the package metadata — unlicensed or custom-licensed packages may not be detected
- `fail-on-scopes: runtime` excludes devDependencies from failing the check, but they're still reported
- The action can only review ecosystems supported by GitHub's dependency graph (npm, pip, gem, cargo, go, composer, NuGet, maven)

## Related
- `dependabot-config.md`
- `github-sbom-generation.md`
- `github-security-advisories.md`
