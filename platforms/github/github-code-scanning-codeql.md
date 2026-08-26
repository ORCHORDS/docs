# github-code-scanning-codeql

**Issue:** Setting up CodeQL code scanning to detect security vulnerabilities in pull requests
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Security vulnerabilities (SQL injection, XSS, path traversal, insecure deserialization) are caught too late — in production or by external pen tests. CodeQL static analysis finds vulnerability patterns at PR time.

## Pattern / Solution
GitHub provides a default CodeQL workflow via Security → Code Scanning → Set up → Default. For full control, add a custom workflow.

**Basic CodeQL workflow:**
```yaml
name: CodeQL

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 6 * * 1'    # weekly full scan on Monday

permissions:
  security-events: write
  contents: read
  actions: read

jobs:
  analyze:
    name: Analyze
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        language: [javascript-typescript, python]
        # Options: c-cpp, csharp, go, java-kotlin, javascript-typescript, python, ruby, swift

    steps:
      - uses: actions/checkout@v4

      - name: Initialize CodeQL
        uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
          queries: security-extended    # security-and-quality for broader coverage

      - name: Autobuild
        uses: github/codeql-action/autobuild@v3
        # For compiled languages (C, Java, etc.) this may need manual build steps

      - name: Perform CodeQL Analysis
        uses: github/codeql-action/analyze@v3
        with:
          category: '/language:${{ matrix.language }}'
```

**Custom query packs:**
```yaml
      - uses: github/codeql-action/init@v3
        with:
          languages: javascript-typescript
          packs: |
            codeql/javascript-queries
            myorg/custom-security-queries@1.0.0
```

**Excluding paths from scanning:**
```yaml
# .github/codeql/codeql-config.yml
paths-ignore:
  - 'node_modules'
  - '**/*.test.ts'
  - 'vendor/**'
```
```yaml
      - uses: github/codeql-action/init@v3
        with:
          config-file: .github/codeql/codeql-config.yml
```

## Gotchas
- CodeQL for compiled languages (C, C++, Java) requires the actual build to run — `autobuild` attempts to infer the build command but often fails for complex projects; provide manual build steps
- Results appear in the Security → Code Scanning tab, not as PR comments — configure "Only blocking" alert severity to fail the check
- The free tier for public repos includes CodeQL; private repos require GitHub Advanced Security (GHAS)
- `security-extended` queries catch more but produce more false positives than the default `security-and-quality` set
- CodeQL analysis for large repos can take 20–60 minutes; the weekly schedule scan is separate from per-PR scans

## Related
- `github-secret-scanning.md`
- `github-security-advisories.md`
- `github-sbom-generation.md`
