# Enforcing CVSS Thresholds with the Dependency Review Action

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Pull requests that add or upgrade npm/pnpm packages sometimes introduce dependencies with known CVEs; you need a mandatory CI check that blocks merge when newly introduced vulnerabilities exceed a configurable CVSS score threshold, with escalating rules per environment.

## Context
GitHub's `dependency-review-action` compares the dependency graph of the base branch against the PR branch and surfaces newly introduced vulnerabilities sourced from the GitHub Advisory Database. It supports blocking on minimum CVSS severity, license allowlists, and specific CVE denylist entries. Combining it with environment-specific configuration files and PR annotations gives security teams a single, auditable enforcement layer without requiring GHAS Advanced Security beyond the free dependency review entitlement.

## Basic Workflow

```yaml
# .github/workflows/dependency-review.yml
name: Dependency Review

on:
  pull_request:
    types: [opened, synchronize, reopened]
    paths:
      - '**/package.json'
      - '**/pnpm-lock.yaml'
      - '**/yarn.lock'
      - '**/package-lock.json'

permissions:
  contents: read
  pull-requests: write   # for PR annotations
  security-events: write # for SARIF upload

jobs:
  dependency-review:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4

      - name: Dependency Review
        uses: actions/dependency-review-action@v4
        with:
          fail-on-severity: high
          deny-licenses: GPL-2.0, GPL-3.0, AGPL-3.0
          comment-summary-in-pr: always
          config-file: '.github/dependency-review-config.yml'
```

## Configuration File

The `config-file` parameter externalises policy so it can differ per environment or be overridden without editing the workflow.

```yaml
# .github/dependency-review-config.yml
fail-on-severity: high

fail-on-scopes:
  - runtime

allow-licenses:
  - MIT
  - Apache-2.0
  - BSD-2-Clause
  - BSD-3-Clause
  - ISC
  - 0BSD
  - BlueOak-1.0.0

deny-packages:
  - pkg:npm/event-stream@3.3.6   # historic supply-chain attack

vulnerability-check: true
license-check: true

comment-summary-in-pr: always
```

## Tiered Severity by Target Branch

Use a matrix or conditional step to apply tighter thresholds when merging to `main` versus feature branches.

```yaml
jobs:
  dependency-review:
    runs-on: ubuntu-24.04
    strategy:
      matrix:
        include:
          - branch_pattern: 'main'
            severity: 'medium'
          - branch_pattern: 'release/**'
            severity: 'medium'
          - branch_pattern: '**'
            severity: 'high'
    steps:
      - uses: actions/checkout@v4

      - name: Resolve effective severity threshold
        id: threshold
        run: |
          BASE="${{ github.base_ref }}"
          if [[ "$BASE" == "main" || "$BASE" == release/* ]]; then
            echo "severity=medium" >> "$GITHUB_OUTPUT"
          else
            echo "severity=high" >> "$GITHUB_OUTPUT"
          fi

      - name: Dependency Review
        uses: actions/dependency-review-action@v4
        with:
          fail-on-severity: ${{ steps.threshold.outputs.severity }}
          config-file: '.github/dependency-review-config.yml'
          comment-summary-in-pr: always
```

## SARIF Upload for Security Dashboard

Upload the review results as SARIF so vulnerabilities appear in the **Security > Code scanning** tab alongside CodeQL results.

```yaml
      - name: Dependency Review with SARIF output
        uses: actions/dependency-review-action@v4
        with:
          fail-on-severity: high
          output-format: sarif
          output-file: dependency-review.sarif
          config-file: '.github/dependency-review-config.yml'

      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v3
        if: always()   # upload even when the review fails
        with:
          sarif_file: dependency-review.sarif
          category: dependency-review
```

## Exemption Workflow for False Positives

When a CVE affects only a code path you don't use, a repository maintainer can add a time-boxed exemption without disabling the gate entirely.

```yaml
# .github/dependency-review-config.yml (with exemption)
allow-ghsas:
  - GHSA-xxxx-yyyy-zzzz   # CVE-2026-12345: affects optional ESM loader path only, not used in this project
                           # Exemption expires: 2026-11-01, Owner: @security-team
```

A linting job enforces that every exemption has an expiry comment:

```yaml
  lint-exemptions:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - name: Check exemption comments have expiry dates
        run: |
          python3 - <<'EOF'
          import re, sys
          text = open('.github/dependency-review-config.yml').read()
          ghsa_lines = [l for l in text.splitlines() if 'GHSA-' in l and not l.strip().startswith('#')]
          errors = []
          for i, line in enumerate(ghsa_lines):
            context_block = '\n'.join(text.splitlines()[max(0, text.splitlines().index(line)-1):text.splitlines().index(line)+3])
            if not re.search(r'expires?:?\s+\d{4}-\d{2}-\d{2}', context_block, re.IGNORECASE):
              errors.append(f"GHSA exemption on line has no expiry date: {line.strip()}")
          if errors:
            print('\n'.join(errors))
            sys.exit(1)
          print("All exemptions have expiry dates.")
          EOF
```

## Cloudflare Workers npm Ecosystem Considerations

When using Workers with the `workerd` runtime, some Node.js polyfill packages (like `node-fetch`, older `undici`) carry CVEs that do not apply in the Workers runtime. Use the `fail-on-scopes` setting to exclude development-only vulnerabilities:

```yaml
fail-on-scopes:
  - runtime      # only fail on runtime dependencies, not devDependencies
```

For monorepos with separate `packages/worker` and `packages/api` workspaces, run separate review jobs scoped to each workspace:

```yaml
  - name: Review worker package dependencies only
    uses: actions/dependency-review-action@v4
    with:
      base-ref: ${{ github.event.pull_request.base.sha }}
      head-ref: ${{ github.event.pull_request.head.sha }}
      config-file: 'packages/worker/.github/dependency-review-config.yml'
```

## Anti-patterns
- Setting `fail-on-severity: critical` only — high-severity vulnerabilities in a runtime dependency are exploitable even without a critical CVE.
- Using `allow-ghsas` as a permanent bypass rather than a time-boxed exemption — old exemptions accumulate and the policy becomes unauditable.
- Not uploading SARIF — without it, security teams cannot track open vulnerabilities in the Code Scanning dashboard.
- Applying the same threshold to development and production branches — tighter thresholds on `main` and `release/*` while allowing `high` on feature branches is a reasonable graduated policy.
- Excluding `pnpm-lock.yaml` from the path filter — the action needs the lockfile to resolve transitive dependency CVEs.

## Gotchas
- `dependency-review-action` only evaluates newly introduced dependencies in the PR diff; pre-existing vulnerabilities in the base branch are not reported here (use Dependabot or a scheduled scan for that).
- The action requires that the repository has the **Dependency graph** feature enabled (Settings > Security > Dependency graph).
- SARIF upload via `github/codeql-action/upload-sarif` requires `security-events: write` permission; workflows triggered by `pull_request` from forks do not have this permission by default — use `pull_request_target` with caution and SHA-pin the action.
- `fail-on-scopes: runtime` uses the `pnpm-lock.yaml` dev/prod scope metadata; packages hoisted to the root workspace may be misclassified.

## Verification
1. Open a PR that adds `"lodash": "4.17.15"` (has known low CVEs) — confirm the review passes when `fail-on-severity: high`.
2. Add a package with a known high CVE and confirm the check blocks the PR and posts a PR comment.
3. Add the GHSA ID to `allow-ghsas` with a future expiry comment and rerun — confirm the check passes.
4. Trigger a merge to `main` branch — confirm the threshold tightens to `medium` via the branch-aware step.

## Related
- `github-dependency-review.md`
- `github-actions-security-hardening.md`
- `github-advanced-security-setup.md`
- `github-dependabot-cooldown-security-boundary.md`
- `github-code-scanning-sarif-category-identity.md`

## Sources
- https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/about-dependency-review
- https://github.com/actions/dependency-review-action
- https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/configuring-the-dependency-review-action
