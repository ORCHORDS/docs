# OWASP Top 10:2025 Exceptional Condition and Fail-Secure Review Template

Use this record to review how an application prevents, detects, and responds to exceptional conditions using OWASP Top 10:2025 A10 as risk guidance. Do not place secrets, production stack traces, or sensitive incident data in the public record.

## Review metadata

- Application/service: `<name>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Critical transaction/state flows: `<references>`
- Error-handling standard/reference: `<reference>`

## Exceptional-condition matrix

| Condition class | Representative trigger | Expected safe state/result | Detected? | Fails closed/securely? | Public error controlled? | Recovery/rollback evidence |
| --- | --- | --- | --- | --- | --- | --- |
| Missing/invalid input | `<trigger>` | `<result>` | `<yes/no>` | `<yes/no>` | `<yes/no>` | `<reference>` |
| Insufficient privilege | `<trigger>` | `<result>` | `<yes/no>` | `<yes/no>` | `<yes/no>` | `<reference>` |
| Dependency/network failure | `<trigger>` | `<result>` | `<yes/no>` | `<yes/no>` | `<yes/no>` | `<reference>` |
| Resource/memory/timing issue | `<trigger>` | `<result>` | `<yes/no>` | `<yes/no>` | `<yes/no>` | `<reference>` |
| Unexpected/null/state condition | `<trigger>` | `<result>` | `<yes/no>` | `<yes/no>` | `<yes/no>` | `<reference>` |

## Review checks

- [ ] Exceptional conditions are handled close enough to the failing operation to preserve a known safe state.
- [ ] Missing or malformed inputs do not drive the application into undefined or partially authorized behavior.
- [ ] Authorization/privilege failures fail closed rather than continuing with reduced checks.
- [ ] Dependency, network, timeout, or resource failures do not silently commit partial state where atomicity is required.
- [ ] Security-sensitive transactions have explicit rollback, compensation, or reconciliation behavior when an operation fails partway through.
- [ ] Public error responses are controlled and do not expose sensitive implementation detail.
- [ ] Error/exception logs provide enough internal diagnostic context for investigation without leaking that context publicly.
- [ ] Unhandled exceptions and panic/crash paths are exercised in test or fault-injection scenarios appropriate to the system.
- [ ] Recovery after a fault returns the system to a documented state rather than assuming a restart makes state consistent.

## Fault exercise evidence

- Fault/exception injected: `<condition>`
- Expected safe behavior: `<expected>`
- Actual behavior: `<result>`
- State/transaction verification: `<reference>`
- Public response verification: `<reference>`
- Internal diagnostic evidence: `<reference>`
- Remediation/retest: `<reference>`

## Source

- OWASP Top 10:2025 A10 — Mishandling of Exceptional Conditions: https://owasp.org/Top10/2025/A10_2025-Mishandling_of_Exceptional_Conditions/
