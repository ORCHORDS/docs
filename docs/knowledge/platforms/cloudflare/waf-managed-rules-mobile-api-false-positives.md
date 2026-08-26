# waf-managed-rules-mobile-api-false-positives

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Mobile API clients (React Native, Expo) receive HTTP 403 with
a Cloudflare-generated error page (Ray ID present, no origin
response body). Desktop browsers calling the same endpoints
succeed. `wrangler tail` shows no inbound request — the block
fires at the edge before the Worker runs.

Affected paths: `POST /api/v1/wallet/link` (Solana address in
body), `POST /api/v1/kyc/submit` (multipart, no Referer),
`GET /api/v1/tx/:address` (base58 path param). Error codes
observed: 1010, 1012, or none when a Workers catch-all
re-wraps the response.

## Context

example project (133+ Worker route handlers) serves a Solana-native
mobile app and a KYC onboarding flow. The traffic profile that
stresses the WAF:

- **Solana addresses.** Base58-encoded 32–44-char strings in
  path params and JSON values; substrings tokenise as SQL
  inside libinjection.
- **No Referer header.** Mobile apps never send Referer;
  OWASP CRS anomaly rules score its absence.
- **Compact JSON + non-standard Content-Type.** Protobuf-JSON
  produces minified bodies; some endpoints accept
  `application/cbor` or `application/vnd.api+json`.
- **JWT in Authorization, no session cookie.** Removes the
  `__cf_bm` smoothing signal that reduces bot-score FPs.
- **KYC multipart.** Binary image parts arrive with no Origin
  header from the mobile HTTP runtime.

## OWASP Core Ruleset anomaly scoring model

CRS v3.x uses anomaly scoring: each matched rule adds to a
running total; once it meets the configured threshold the
request is blocked. Mobile requests accumulate score fast:

```
OWASP rule  Message                      +pts  Mobile trigger
----------  ---------------------------  ----  ----------------
920300      Missing Accept header           3  stripped by libs
920320      Missing/empty User-Agent        3  custom HTTP libs
920230      Multiple/missing Referer        3  apps never send
941100      SQLi via libinjection           5  base58 strings
941130      SQLi keyword heuristic          5  OR/AND in b58
932100      Unix RCE shell pattern          5  pipes URL-encoded
913100      Known scanner user-agent        5  mobile UA match
```

A mobile POST with no Referer (+3), compact Accept (+3), and
a Solana address in the body (+5) scores 11 before any attack
is present. At PL2 (Medium, threshold 40) further header-
anomaly rules push Solana payloads to 25–35.

## Solana base58 and SQLi false positives

Rule 941100 runs libinjection on every decoded request value.
Base58 uses A-Z, a-z, 1-9 (no 0, O, I, l). Substrings `OR`,
`AND`, `IN`, `AS`, and `IS` appear in ~18 % of base58 strings
≥ 32 chars and parse as SQL keywords even inside a JSON-quoted
value. Uppercase runs tokenise as SQL identifiers; adjacent
digit runs match numeric literals — together they form valid
SQL AST fragments. Scope exceptions to `/api/v1/wallet/*` and
`/api/v1/tx/*`, not the entire `/api/*` tree.

## Skip rules vs. WAF exceptions: which primitive to use

```
Mechanism        Phase            What it bypasses
---------------  ---------------  ---------------------------------
WAF exception    Managed rules    One ruleset, specific rule IDs,
(Exceptions tab) phase only       or rule tags. Must precede the
                                  execute action in the phase.

Custom rule      Custom rules     Any WAF product: managed rules,
with Skip action (fires before    rate limiting, BIC, Zone
                 managed rules)   Lockdown. Widest blast radius.
```

Use a **WAF exception** for single-rule suppression (e.g.
disable 941100 on `/api/v1/tx/*` only). Use a **custom Skip
rule** when no managed rule should run for a machine-to-
machine path. Example expression:

```text
(
  http.request.uri.path matches "^/api/v1/"
  and http.request.headers["authorization"]
      matches "^Bearer [A-Za-z0-9._-]+"
)
```

Action → Skip → CF Managed Ruleset, OWASP Ruleset.
Omit `ratelimit` from Skip products unless a Workers-side
rate limiter already covers the path.

## OWASP sensitivity / paranoia-level tuning

```
Label    PL   Threshold  Recommendation
-------  ---  ---------  ------------------------------------
High     PL3  25         Blocks nearly all mobile API traffic
Medium   PL2  40         Default; blocks Solana payloads
Low      PL1  60         Best for API zones; retains SQLi
                         detection, drops header-absence rules
```

Set **PL1 + threshold 60** for API-only zones via Security →
WAF → Managed Rules → OWASP → Sensitivity. In Terraform set
`sensitivity_level = "low"` in the OWASP ruleset override
block. The CF Managed Ruleset runs independently and handles
the modern attack corpus; rely on it for injection detection.

## WAF → Rate Limit → Bot Management evaluation order

```
Step  Phase                         Product
----  ----------------------------  ----------------------------
 1    ddos_l7                       HTTP DDoS protection
 2    http_request_firewall_custom  Custom Rules ← Skip here
 3    http_ratelimit                Rate Limiting Rules
 4    http_request_firewall_managed CF + OWASP Managed Rules
 5    http_request_sbfm             Super Bot Fight Mode /
                                    Bot Management (Enterprise)
```

- A Skip rule in step 2 blocks managed rules (step 4) from
  running. Rate limiting (step 3) still runs unless `ratelimit`
  is included in the Skip products list.
- Bot Management runs last (step 5). Native apps never execute
  the JSD beacon — bot score can reach 1 even after WAF passes
  the request. Add a `log`-mode rule on API paths when JSD is
  on.
- `cf.waf.score.sqli` / `.xss` / `.rce` are independent of
  the managed rulesets. They do not block unless a custom rule
  acts on them. Treat as a signal, not a gate.

## Logpush → R2: identifying rule IDs causing FPs

Security Events retains 72 hours. For sustained triage add a
Logpush job on the `firewall_events` dataset to an R2 bucket,
including fields: `Action`, `RuleID`, `RuleMessage`,
`ClientRequestPath`, `WAFScore`, `Matches`.

After loading into D1 or any SQL engine:

```sql
SELECT RuleID, RuleMessage, COUNT(*) AS hits
FROM firewall_events
WHERE Action = 'block'
  AND ClientRequestPath LIKE '/api/v1/%'
GROUP BY RuleID, RuleMessage
ORDER BY hits DESC LIMIT 20;
```

OWASP rule IDs appear as 6-digit codes (9xxxxx) in `RuleID`.
`WAFScore` is the anomaly total; `Matches` lists every rule
that contributed — check it for partial scores, not only the
rule that crossed the threshold.

## Anti-patterns

- **Disabling the entire OWASP ruleset.** Lower sensitivity
  to PL1 instead; disabling also removes real injection rules.
- **IP Access Rule Allow to unblock devices.** Bypasses managed
  rules, rate limiting, and custom rules globally — blast
  radius is the whole zone, not just the FP path.
- **Catch-all exception on `/api/*`.** Suppresses injection
  detection across the full API. Scope to wallet/tx paths.
- **Testing exceptions in Log mode only.** No request is
  blocked in Log mode; test against known-bad payloads in
  Block mode.

## Gotchas

- **WAFScore 0 ≠ clean.** When OWASP is skipped, `WAFScore`
  is 0. Check the `Action` field, not the score.
- **Bot score 0 after Skip.** A Skip rule covering Bot
  Management logs `cf.bot_management.score = 0` —
  "not computed", not "verified human".
- **API Shield schema validation is a separate gate.** Skip
  rules do not bypass schema validation; a base58 address
  where the schema declares `format: uuid` still returns 400.
- **Rule drift.** CF publishes managed-rules changelogs
  weekly. Re-run the Logpush query after each release.

## Verification

1. In Block mode, POST a Solana address to the affected path.
   Confirm the exception passes the request: Security Events
   shows action = allow and the request appears in
   `wrangler tail`.
2. POST `'; DROP TABLE t;--` to the same path. Confirm it is
   still blocked — the exception must not over-scope.
3. In Logpush R2 output confirm `Action = "allow"` and
   `RuleID` names the exception rule, not an empty string.
4. After each CF managed-rules changelog, re-run the SQL
   query and diff top-20 rule IDs against the baseline.

## Related

- `cloudflare/waf-managed-rules-exception-order-and-future-rule-drift.md`
- `cloudflare/bot-management-enterprise.md`
- `cloudflare/api-shield-schema-validation-2-rollout.md`
- `cloudflare/waf-rate-limiting-deep-dive.md`
- `cloudflare/waf-best-practices.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/waf/managed-rules/
- https://developers.cloudflare.com/waf/managed-rules/reference/owasp-core-ruleset/
- https://developers.cloudflare.com/waf/managed-rules/reference/owasp-core-ruleset/concepts/
- https://developers.cloudflare.com/waf/managed-rules/troubleshooting/
- https://developers.cloudflare.com/waf/managed-rules/waf-exceptions/
- https://developers.cloudflare.com/waf/feature-interoperability
- https://developers.cloudflare.com/waf/analytics/security-events/
- https://developers.cloudflare.com/logs/logpush/logpush-job/datasets/zone/firewall_events/
- https://developers.cloudflare.com/api-shield/security/schema-validation/
- https://developers.cloudflare.com/ruleset-engine/rules-language/fields/reference/cf.waf.score.sqli/
