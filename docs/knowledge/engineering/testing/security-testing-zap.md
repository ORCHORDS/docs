# security-testing-zap

**Issue:** Automating OWASP vulnerability scanning as part of the CI pipeline
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Security testing happens only at penetration test engagements, missing vulnerabilities introduced between tests.

## Pattern / Solution
OWASP ZAP (Zed Attack Proxy) can run automated baseline scans in CI:

```yaml
# GitHub Actions
- name: ZAP Baseline Scan
  uses: zaproxy/action-baseline@v0.12.0
  with:
    target: "https://staging.example.com"
    rules_file_name: ".zap/rules.tsv"
    fail_action: false   # warn-only; switch to true for hard gate
```

The baseline scan covers passive checks (no active attacks): missing security headers, exposed sensitive fields, insecure cookies.

For API scanning:
```yaml
- uses: zaproxy/action-api-scan@v0.7.0
  with:
    target: "https://staging.example.com/api/openapi.json"
```

Suppress known false positives via the rules file and track them in a separate security backlog.

## Gotchas
- Run scans against a staging environment, never production — active scans can create, modify, or delete data.
- ZAP baseline scans miss authentication-gated endpoints; configure a session token for authenticated scans.
- DAST (dynamic scanning) complements but does not replace SAST tools (ESLint security plugins, Semgrep).

## Related
- dependency-scanning-tests
- integration-test-api
- test-environment-management
