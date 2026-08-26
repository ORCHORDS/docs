# Semgrep Custom Rules for Security and Code Quality in CI

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

ESLint catches style violations; TypeScript catches type errors;
neither catches security anti-patterns like raw SQL string
interpolation next to user input, secrets committed in source, JWT
verification bypasses, or the team's domain-specific no-go patterns
(e.g., calling a deprecated internal API that still compiles but
produces incorrect billing records). Code review catches some of
these but review is inconsistent and expensive at scale.

## Context

The platform team maintains a growing Worker fleet with shared
patterns around D1 queries, KV access, and webhook signature
verification. Semgrep enforces those patterns automatically.
Registry rules cover OWASP top-10 for JavaScript and TypeScript.
Custom rules encode team conventions that no generic ruleset knows
about. Both run in GitHub Actions on every PR. The team's Semgrep
config lives in `semgrep/` at the repo root — checked in, reviewed
like code.

## Rule YAML Pattern Syntax

A rule is a YAML document with a `rules` list. Key clauses:
`pattern` (match this shape), `pattern-not` (exclude this shape),
`pattern-either` (match any of a list), `pattern-inside` (match
only inside a container), `focus-metavariable` (report a capture's
location). Example — block raw template-literal D1 queries:

```yaml
# semgrep/rules/d1-no-raw-interpolation.yaml
rules:
  - id: d1-no-raw-string-interpolation
    patterns:
      - pattern: $DB.prepare(`...${...}...`)
      - pattern-not: $DB.prepare($QUERY).bind(...)
    message: "Use db.prepare(sql).bind(value) instead."
    languages: [typescript, javascript]
    severity: ERROR
    metadata:
      cwe: "CWE-89"
```

## Metavariables and Ellipsis

`$NAME` binds a single AST node; `$...NAME` binds zero or more
(variadic); `...` matches any sequence of statements or arguments.
`focus-metavariable` pins the reported location to a captured node:

```yaml
rules:
  - id: no-user-id-from-header
    patterns:
      - pattern: |
          const $ID = $REQ.headers.get("x-user-id");
          ...
          $DB.prepare($Q).bind(..., $ID, ...)
    focus-metavariable: $ID
    message: "Validate user ID from session before DB use."
    languages: [typescript]
    severity: ERROR
```

## Taint Analysis

`mode: taint` tracks a value from `pattern-sources` to
`pattern-sinks` through assignments and calls within a single file.
Cross-file taint requires Semgrep Pro.

```yaml
rules:
  - id: taint-user-input-to-kv-key
    mode: taint
    pattern-sources:
      - pattern: $REQ.url
      - pattern: $REQ.headers.get(...)
    pattern-sinks:
      - pattern: $KV.get(...)
      - pattern: $KV.put(...)
    pattern-sanitizers:
      - pattern: sanitizeKey($X)
    message: "Unsanitized input in KV key — sanitize first."
    languages: [typescript]
    severity: ERROR
```

Taint rules are 5–20x slower than pattern rules. Run them on a
nightly schedule rather than every PR.

## CI Integration — GitHub Actions

```yaml
# .github/workflows/semgrep.yml
jobs:
  semgrep:
    runs-on: ubuntu-latest
    container: { image: semgrep/semgrep }
    permissions:
      security-events: write
    steps:
      - uses: actions/checkout@v4
      - run: |
          semgrep --config semgrep/rules/ \
            --config p/typescript --config p/secrets \
            --error --sarif --output semgrep.sarif src/
      - uses: github/codeql-action/upload-sarif@v3
        if: always()
        with: { sarif_file: semgrep.sarif }
```

`--error` exits non-zero on `ERROR`-severity findings. The SARIF
upload populates the GitHub Security tab.

## Registry Rules vs Custom Rules

Registry rules (`p/*`) are maintained by the Semgrep team and cover
generic OWASP/CWE patterns. Custom rules are low false-positive but
require authoring. Use both: pin registry configs explicitly in CI.

Recommended for the platform team stack: `p/typescript`,
`p/secrets`, `p/owasp-top-ten`, `p/nodejs`.

## Performance Tuning

```bash
# Scope to changed files only (faster PRs)
git diff --name-only origin/main | grep -E '\.(ts|js)$' | \
  xargs semgrep --config semgrep/rules/ --error

# Exclude slow taint rules from the PR check
semgrep --config semgrep/rules/ \
        --exclude-rule "taint-user-input-to-kv-key" src/
```

Run taint rules on a nightly schedule; run pattern rules on every PR.

## Anti-patterns

- `# nosemgrep` without a justification comment — treat it like
  `eslint-disable`: require a reason in the PR review.
- Rules with only `pattern` and no `pattern-not` when legitimate
  usages exist — false positives erode trust in CI.
- All custom rules in one YAML file — one file per category keeps
  `git blame` meaningful.
- `--config auto` in CI — downloads hundreds of rules per run;
  pin explicit config references instead.

## Gotchas

- Pattern syntax is not regex — `$X` binds an AST node. `"secret"`
  matches only the exact string literal, not a substring.
- `...` in a call (`f(...)`) matches any args; in a block it matches
  any statement sequence — context determines which.
- `pattern-not-inside` excludes matches anywhere inside a container;
  `pattern-not` only excludes same-shape matches. Different scopes.
- SARIF upload requires `security-events: write` in the workflow
  `permissions` block; missing it fails silently.

## Verification

```bash
# Validate rule YAML
semgrep --validate --config semgrep/rules/

# Test one rule against a fixture
semgrep --config semgrep/rules/d1-no-raw-interpolation.yaml \
        --lang typescript test/fixtures/bad-query.ts

# Run all custom rules
semgrep --config semgrep/rules/ --error src/ 2>&1 | head -20
```

## Related

- `devtools/pre-commit-framework.md`
- `security/owasp-top-ten-workers.md`
- `devtools/github-cli-daily-workflow.md`
- `testing/api-contract-testing.md`
- `database/d1-query-patterns.md`

## Source URLs (verified 2026-08-17)

- https://semgrep.dev/docs/writing-rules/rule-syntax/
- https://semgrep.dev/docs/writing-rules/pattern-syntax/
- https://semgrep.dev/docs/semgrep-ci/sample-ci-configs/#github-actions
- https://semgrep.dev/docs/writing-rules/data-flow/taint-mode/
- https://semgrep.dev/r — registry of public rules
