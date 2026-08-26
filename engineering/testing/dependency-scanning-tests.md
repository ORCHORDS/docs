# dependency-scanning-tests

**Issue:** Detecting vulnerabilities in third-party dependencies automatically
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A CVE is published for a dependency already in production, but the team only discovers it weeks later through a security advisory.

## Pattern / Solution
Run dependency audits in CI on every PR and on a nightly schedule:

**npm / pnpm:**
```bash
npm audit --audit-level=high
# fail build on high/critical vulnerabilities
```

**GitHub Dependabot:** Enable in `.github/dependabot.yml` for automatic PRs when vulnerabilities are patched:
```yaml
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/"
    schedule: { interval: "weekly" }
    open-pull-requests-limit: 10
```

**Snyk (more detailed):**
```bash
snyk test --severity-threshold=high
snyk monitor  # continuous monitoring
```

Maintain an `allow-list` (`.snyk` policy file) for accepted risks with documented justification and expiry dates.

## Gotchas
- `npm audit` reports transitive dependencies; most reported vulnerabilities affect dev-only packages or are unexploitable in your context — triage before panicking.
- Auto-merge Dependabot PRs only for patch-level updates with a green test suite.
- `package-lock.json` / `pnpm-lock.yaml` must be committed for reproducible audit results.

## Related
- security-testing-zap
- test-environment-management
- ci-test-parallelization
