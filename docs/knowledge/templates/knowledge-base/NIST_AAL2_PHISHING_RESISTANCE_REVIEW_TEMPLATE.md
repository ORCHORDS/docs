# NIST AAL2 Phishing-Resistance Review Template

Use this record when a service is being assessed against NIST SP 800-63B-4 AAL2. This template records NIST assurance evidence; it does not make AAL2 a universal legal requirement for systems outside that scope.

## Review metadata

- Service/application: `<name>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Claimed/target assurance level: `<AAL2 or other>`
- User populations in scope: `<groups>`

## Authenticator inventory

| Authenticator option | Factor type | Manual code transfer? | Phishing-resistant under NIST? | Available to in-scope users? | Evidence |
| --- | --- | --- | --- | --- | --- |
| `<option>` | `<single/multi-factor>` | `<yes/no>` | `<yes/no>` | `<yes/no>` | `<reference>` |

## Review checks

- [ ] At least one deployed authentication option offered at AAL2 satisfies NIST's phishing-resistance definition.
- [ ] OTP, out-of-band codes, and other manually entered authenticator outputs are not labeled phishing-resistant.
- [ ] MFA status and phishing-resistance status are documented separately.
- [ ] The phishing-resistant option is actually available to the population being assessed, not merely planned.
- [ ] Enrollment and recovery paths do not silently downgrade the assurance claim without a documented policy decision.

## Verification evidence

- Phishing-resistant option exercised end-to-end: `<result/reference>`
- Protocol/verifier binding evidence: `<reference>`
- User availability test: `<result>`
- Documentation/claim review: `<result>`

## Findings and actions

- Findings: `<text>`
- Corrective actions/owner/date: `<text>`
- Retest result: `<result>`

## Source

- NIST SP 800-63B-4, Authenticator and Verifier Requirements: https://pages.nist.gov/800-63-4/sp800-63b.html
