# OWASP Top 10:2025 Application Security Portfolio Baseline Review Template

Use this record to assess whether an organization has a repeatable, risk-based application-security baseline across its application/API portfolio, drawing on OWASP Top 10:2025 application-security program guidance. This is a governance review, not evidence of OWASP certification or endorsement.

## Review metadata

- Portfolio/business unit: `<scope>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Common risk model: `<reference>`
- Application/API inventory source: `<reference>`

## Portfolio inventory and risk tiering

| Application/API class | Owner | Business/data criticality | Risk tier | Required assurance/testing level | Baseline controls applied? | Exceptions | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `<application>` | `<owner>` | `<criticality>` | `<tier>` | `<level>` | `<yes/no>` | `<reference>` | `<reference>` |

## Baseline-program checks

- [ ] Applications and APIs are inventoried with accountable owners and business context.
- [ ] A common risk-rating model uses consistent likelihood/impact factors aligned to organizational risk tolerance.
- [ ] Risk tiering determines the expected assurance depth rather than applying one undifferentiated testing level everywhere.
- [ ] A shared application-security policy/standard establishes minimum development and operational expectations.
- [ ] Reusable security controls, libraries, or patterns are available for common requirements rather than requiring every team to design controls independently.
- [ ] Application-security education is mapped to relevant development/security roles.
- [ ] Security activities are integrated into requirements/design, development, testing, rollout, operations/change management, and retirement.
- [ ] Continuous or recurring security testing expectations are defined according to portfolio risk.
- [ ] Management can see portfolio coverage, exceptions, material findings, aging, and unresolved high-risk gaps.
- [ ] Retired or superseded applications are removed from active exposure/inventory or governed through an explicit retirement process.

## Coverage metrics

- Applications/APIs inventoried: `<count/coverage>`
- Risk-tier assignment coverage: `<coverage>`
- Baseline-control coverage: `<coverage>`
- Required security testing coverage: `<coverage>`
- Open high-risk exceptions/findings: `<count>`
- Stale/retirement candidates: `<count>`

## Findings and actions

- Inventory/ownership gaps: `<text>`
- Risk-model/tiering gaps: `<text>`
- Baseline/control gaps: `<text>`
- Testing/visibility gaps: `<text>`
- Corrective actions/owner/date: `<text>`

## Sources

- OWASP Top 10:2025 — Establishing a Modern Application Security Program: https://owasp.org/Top10/2025/0x03_2025-Establishing_a_Modern_Application_Security_Program/
- OWASP Top 10 project page — current released version and awareness-document scope: https://owasp.org/www-project-top-ten/
