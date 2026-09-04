# CISA Privileged MFA Default Review Template

Use this record to review privileged-user MFA availability and default behavior against CISA/NSA Secure by Design recommendations. Preserve product-specific sensitive configuration details in protected evidence.

## Review metadata

- Product/service: `<name>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Privileged roles in scope: `<roles>`
- Baseline commercial tier/configuration: `<description>`

## Privileged authentication inventory

| Privileged path | MFA available? | Enabled/required by default? | Phishing-resistant option available? | Additional paid tier required? | Evidence |
| --- | --- | --- | --- | --- | --- |
| Admin console | `<yes/no>` | `<status>` | `<yes/no>` | `<yes/no>` | `<reference>` |
| API/CLI administration | `<yes/no>` | `<status>` | `<yes/no>` | `<yes/no>` | `<reference>` |
| Recovery/bootstrap | `<yes/no>` | `<status>` | `<yes/no>` | `<yes/no>` | `<reference>` |

## Review checks

- [ ] MFA is available as a baseline security capability for privileged users.
- [ ] The normal privileged-user setup path does not silently leave new administrators password-only without an explicit security decision.
- [ ] Phishing-resistant authentication is supported where the product risk/platform design calls for it.
- [ ] Protecting privileged users does not depend solely on purchasing an optional security tier.
- [ ] Bootstrap, recovery, support, and break-glass flows are included in the MFA review.
- [ ] Product claims distinguish “supports MFA” from “MFA is secure by default.”

## Verification evidence

- Fresh privileged-account setup test: `<result>`
- Baseline-tier entitlement test: `<result>`
- Recovery/bootstrap MFA test: `<result>`
- Phishing-resistant option test: `<result/not applicable>`

## Findings and actions

- Findings: `<text>`
- Corrective actions/owner/date: `<text>`
- Retest result: `<result>`

## Sources

- NSA/CISA, Top Ten Cybersecurity Misconfigurations — Secure by Design recommendations: https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-278a
- CISA, manufacturer guidance supporting MFA and secure-by-default operation: https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-335a
