# github-ghas-code-scanning

**Issue:** Setting up CodeQL code scanning as part of GHAS
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Code scanning uses CodeQL (or third-party tools) to detect security vulnerabilities in code. Alerts appear in the Security tab and can block PRs.

## Pattern / Solution
`.github/workflows/codeql.yml`:
```yaml
on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: '0 2 * * 1'

jobs:
  analyze:
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      actions: read
      contents: read
    strategy:
      matrix:
        language: [javascript-typescript, python]
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
          queries: security-extended
      - uses: github/codeql-action/autobuild@v3
      - uses: github/codeql-action/analyze@v3
```

## Gotchas
- `security-events: write` permission is required to upload SARIF results.
- `autobuild` works for compiled languages; for interpreted languages (JS, Python) it is optional.
- `queries: security-extended` adds more checks than the default suite at the cost of more false positives.
- Schedule the weekly scan because new queries are released regularly.
- SARIF files from third-party tools (Semgrep, Trivy) can also be uploaded with `github/codeql-action/upload-sarif`.

## Related
- `github-advanced-security-setup.md`
- `github-code-scanning-codeql.md`
