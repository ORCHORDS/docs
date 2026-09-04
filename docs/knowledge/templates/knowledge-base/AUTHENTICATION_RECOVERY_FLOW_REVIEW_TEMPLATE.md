# Authentication and Recovery Flow Review Template

Use this record to review login, credential recovery, token handling, and sensitive account changes as one authentication surface. Do not include real credentials, recovery tokens, or personal account data.

## Review metadata

- Application/API: `<name>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Authentication mechanisms in scope: `<list>`

## Authentication-flow inventory

| Flow | Entry point | Credential/proof type | Rate/attempt control | Success invalidation or rotation |
| --- | --- | --- | --- | --- |
| Login | `<endpoint>` | `<password/MFA/etc.>` | `<control>` | `<behavior>` |
| Forgot password | `<endpoint>` | `<proof>` | `<control>` | `<behavior>` |
| Reset password | `<endpoint>` | `<recovery token>` | `<control>` | `<behavior>` |
| Sensitive account change | `<endpoint>` | `<fresh auth proof>` | `<control>` | `<behavior>` |

## Review checks

- [ ] Forgot/reset-password flows receive authentication-grade brute-force and rate-limit protection.
- [ ] Recovery responses avoid unnecessary account-enumeration signals.
- [ ] Recovery credentials are generated, validated, expired, and invalidated according to the chosen authentication design.
- [ ] Authentication tokens and passwords are not carried in URLs.
- [ ] Token authenticity and expiry are validated at every authentication boundary.
- [ ] Sensitive changes to email, password, MFA factors, or recovery configuration require appropriate fresh authentication.
- [ ] Alternate clients, batching, protocol features, or secondary authentication endpoints do not bypass attempt controls.

## Abuse testing

- Repeated login attempt result: `<result>`
- Repeated recovery attempt result: `<result>`
- Alternate-path/batching test: `<result>`
- Sensitive-account-change reauthentication test: `<result>`

## Findings and actions

- Findings: `<text>`
- Corrective actions/owner/date: `<text>`
- Retest result: `<result>`

## Source

- OWASP API2:2023 Broken Authentication: https://owasp.org/API-Security/editions/2023/en/0xa2-broken-authentication/
