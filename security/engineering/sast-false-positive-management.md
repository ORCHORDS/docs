# sast-false-positive-management

**Issue:** High SAST false positive rates cause alert fatigue, leading developers to ignore real vulnerabilities
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Static analysis tools (Semgrep, CodeQL, SonarQube, Checkmarx) generate findings that developers learn to dismiss because most are irrelevant. When a real vulnerability appears alongside 200 false positives, it gets ignored too.

## Pattern / Solution
```yaml
# Semgrep — suppress false positive with inline comment
result = exec_command(user_input)  # nosemgrep: arbitrary-code-execution
# Only suppress after human review confirms it's safe

# .semgrep.yml — tune rules to reduce noise
rules:
  - id: sql-injection
    severity: ERROR
    # Narrow the pattern to avoid matching parameterized queries
    pattern: |
      db.execute("..." + $VAR)
    # Exclude test files
    paths:
      exclude:
        - "tests/"
        - "**/*.test.js"
```
```bash
# Track suppression rationale in comments
# SECURITY-SKIP: user_input is validated by InputValidator.sanitize() on L45
```
```python
# Workflow: triage findings weekly
# 1. Auto-close confirmed false positives with tag + reason
# 2. Escalate HIGH/CRITICAL to engineering lead within 24h
# 3. Track suppression rate — >30% FP rate means rule needs tuning
```

## Gotchas
- Inline suppression comments become a vulnerability if not reviewed — require PR approval for each `nosemgrep` or `// NOSONAR`.
- SAST tools miss runtime vulnerabilities (e.g., SSRF via configuration) — complement with DAST.
- Findings in auto-generated code (protobuf, ORM migrations) should be excluded at path level, not suppressed inline.
- Tuning rules to reduce FPs can also reduce true positive detection — validate with known-vulnerable test cases.

## Related
- `dast-automated-scanning.md`
- `threat-modeling-stride.md`
