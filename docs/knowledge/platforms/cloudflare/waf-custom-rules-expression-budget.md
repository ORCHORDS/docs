# WAF Custom Rules Expression Budget

A WAF custom rule is an expression in the Cloudflare rules language evaluated against incoming traffic, plus an action to take when it matches. Expressions are cheap individually, but a ruleset is evaluated at scale, on every request, and the budget for complexity is finite: rules have length and syntax constraints, the rules language supports a defined set of fields and functions, and every additional expression in a phase adds evaluation cost and review burden. Teams that treat the custom rules list as a notepad — appending a rule per incident, never consolidating — eventually hit expression limits, unexplainable match behavior, and a ruleset nobody can reason about. This article defines how to spend the expression budget deliberately.

## Scope

Covers authoring and governing WAF custom rules: expression language constraints, complexity and size budgets, phase placement of custom rules (the `http_request_firewall_custom` phase), and consolidation discipline. Applies to zones using the Cloudflare WAF custom rules product via dashboard or API. Excludes managed rules and WAF attack score logic, rate limiting rules (a different product with its own expression handling), and Ruleset Engine phase ordering methodology beyond the custom phase itself.

## Workflow or implementation guidance

1. Express the security intent before writing syntax: one sentence per rule ("block logins from these three countries outside business hours", "challenge user agents matching this scraper signature"). If the intent cannot be stated in one sentence, the rule is several rules.
2. Draft the expression using the documented rules language: field references (`http.request.uri.path`, `ip.geoip.country`, `cf.threat_score`, and similar), operators, and functions limited to the supported set. Verify each field exists in the documentation before relying on it — guessed field names fail at save time or, worse, never match.
3. Check size and syntax against the documented limits: expressions have a maximum length, and rulesets have a maximum number of rules per phase. Long OR-chains over the same field should become a lookup-style construct where the language supports it, or the values consolidated into fewer comparisons.
4. Place the rule in the right phase context. Custom firewall rules evaluate in the `http_request_firewall_custom` phase; rules that must run before or after other products' rules (transforms, redirects, managed WAF) depend on that phase order, so the rule's position expectations must be stated, not assumed.
5. Test with the expression preview or a staged deployment: run the expression against sample requests (a sampling of real traffic or crafted probes) and confirm it matches exactly the intended population and nothing else. A rule that over-matches is an outage with a delay.
6. Deploy with a low-blast-radius action first where feasible — log action before block — observe match volume for a soak period, then tighten to the enforcing action.
7. Record each rule's intent sentence, owner, and review date in the ruleset register, and schedule consolidation: quarterly, merge overlapping expressions, delete expired incident rules, and re-check total ruleset size against limits.

## Controls

- Intent-first authoring rule: every rule has a one-sentence purpose recorded before syntax review.
- Field verification requirement: expressions may only reference fields documented for the phase; reviewers check unfamiliar fields against the reference.
- Size and count tracking: the register tracks expression lengths and total rule count per phase against the documented limits, alerting at a defined threshold.
- Log-before-enforce gate: new blocking rules pass through a log-action soak unless an active incident justifies immediate enforcement with named approval.
- Consolidation cadence: quarterly review merges duplicates, retires expired rules, and documents the deltas.
- Phase-expectation note: each rule records whether its behavior depends on ordering relative to other products' rules.

## Validation evidence

- Ruleset register export: rule IDs, intent sentences, expressions, owners, actions, and review dates.
- Expression preview or test-harness results showing match and non-match cases for each new rule before enforcement.
- Size and count telemetry: per-expression lengths and phase rule counts against limits, from the register or API.
- Log-action soak output: match volume and sampled request characteristics during the observation period.
- Enforcement change record: the transition from log to block with the approving owner and date.
- Quarterly consolidation diff: rules merged, deleted, or modified with rationale.

## Failure modes and correction

- Expression rejected for length or syntax at save: split into multiple rules with the same intent, or consolidate the value list into fewer comparisons; do not shorten by deleting conditions silently.
- Rule silently never matches: a guessed or deprecated field name, wrong operator, or case mismatch in a string comparison; fix against the field reference and re-run the preview tests.
- Rule over-matches and blocks legitimate traffic: revert to log action immediately, tighten the expression with the observed false-positive population, and re-soak.
- Ruleset hits the per-phase rule limit: consolidation is overdue; merge overlapping incident rules and retire expired ones before adding anything new.
- Ordering surprise: a custom rule assumed to run after a transform saw the untransformed request (or vice versa); record phase expectations per rule and validate with a crafted request pair.
- Accumulated incident rules nobody dares delete: the quarterly cadence forces expiry decisions with owners named; a rule without an owner is deleted or re-owned, not carried forever.

## Limitations

- Expression length, rules-per-phase, and language feature limits are product-defined and may change; the register's threshold approach absorbs drift by re-checking against current documentation.
- The rules language supports a defined field and function set; logic outside it must be expressed differently (multiple rules or another product).
- Match behavior depends on phase context; expressions correct in isolation can behave differently relative to other products' rules.
- Preview testing approximates production traffic; low-frequency edge cases can still escape detection until observed live.
- Dashboard and API views of the ruleset should agree, but reconciliation is manual if edits are made in both.

## Canonical sources

- Cloudflare WAF docs, "Custom rules": https://developers.cloudflare.com/waf/custom-rules/
- Cloudflare Ruleset Engine docs, "Phases list" (phase context including the custom firewall phase): https://developers.cloudflare.com/ruleset-engine/reference/phases-list/
