# dast-automated-scanning

**Issue:** Static analysis misses runtime vulnerabilities that only manifest under actual HTTP traffic
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
SAST tools analyze source code but cannot detect vulnerabilities that depend on runtime behavior — authentication bypasses, SSRF via redirect chains, business logic flaws, or misconfigured middleware. DAST (Dynamic Application Security Testing) sends real HTTP requests against a running app.

## Pattern / Solution
```yaml
# GitHub Actions — OWASP ZAP baseline scan
- name: ZAP Scan
  uses: zaproxy/action-baseline@v0.12.0
  with:
    target: 'https://staging.app.example.com'
    rules_file_name: '.zap/rules.tsv'
    cmd_options: '-a'  # include ajax spider

# .zap/rules.tsv — tune false positives
# RULE_ID  ALERT_LEVEL
# 10202    IGNORE   # Absence of Anti-CSRF Tokens (handled by custom middleware)
```
```bash
# Nuclei for targeted CVE/misconfiguration scanning
nuclei -u https://staging.app.example.com -t cves/ -t misconfigurations/ -o nuclei-results.json

# Burp Suite Enterprise in CI (licensed)
# Headless scan with REST API trigger
curl -X POST https://burp-enterprise/api/v1/scan \
  -d '{"scope": {"include": [{"rule": "https://staging.app.example.com"}]}}'
```

## Gotchas
- DAST must run against a staging/test environment, never production — it will submit forms and trigger state changes.
- Authenticated scanning requires configuring session tokens or login scripts — unauthenticated scans miss most of the attack surface.
- DAST is slow — run a fast baseline scan on every PR, full scan nightly.
- Rate limiting and WAF rules may block scanner traffic — allowlist scanner IPs in staging.

## Related
- `sast-false-positive-management.md`
- `attack-surface-reduction.md`
