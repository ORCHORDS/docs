# CISA Secure by Design bad-practice exception register

**Issue:** A team may endorse secure-by-design principles while continuing risky product defaults through undocumented exceptions, making the policy impossible to audit or retire.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Translate CISA and FBI Product Security Bad Practices guidance into an engineering exception register. The guidance is voluntary for most manufacturers, so describe it as a risk baseline unless a contract or applicable rule makes a requirement binding.

## Controls

- Map each relevant bad practice to products, components, and accountable owners.
- Default to eliminating the practice. An exception requires affected scope, threat scenario, customer impact, compensating controls, approval, expiry, and an exit plan.
- Track unsupported or end-of-life components, default credentials, unsafe memory usage where applicable, delayed remediation of Known Exploited Vulnerabilities, and avoidable vulnerability classes as distinct risks.
- Put expiry reminders and policy tests into normal engineering workflows. Do not keep the only copy in meeting notes.
- Require leadership review for exceptions that expose many customers or critical functions.
- Publish customer-facing security configuration and support-lifecycle information without exposing exploitable internal detail.
- Reassess entries when CISA updates the guidance or a referenced vulnerability becomes known exploited.

## Verification

1. Search repositories and deployment inventories for each in-scope practice.
2. Confirm every detected case has either a remediation issue or a live exception.
3. Exercise a sample compensating control and preserve the result as evidence.
4. Fail review when an exception expires or its owner becomes inactive.
5. Measure open exceptions, age, affected products, and closure rate; a falling count is the intended direction.

## Gotchas

- The register is not permission to normalize bad practices.
- A generic “business need” is not a threat-based justification.
- Eliminating one defect instance is weaker than eliminating its class through safe APIs, frameworks, linters, and tests.
- Avoid reproducing credentials, exploit details, or sensitive architecture in the register.

## Sources

- [CISA and FBI updated Product Security Bad Practices guidance announcement](https://www.cisa.gov/news-events/alerts/2025/01/17/cisa-and-fbi-release-updated-guidance-product-security-bad-practices)
- [CISA Secure by Design](https://www.cisa.gov/securebydesign)
