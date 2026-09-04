# OWASP Top 10:2025 Software Supply Chain Failure Review Template

Use this record to review application software-supply-chain risk against the concepts in OWASP Top 10:2025 A03. The OWASP Top 10 is an awareness document, not a certification standard; this template is for evidence collection and risk review.

## Review metadata

- Application/service: `<name>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Build/release pipeline reference: `<reference>`
- Dependency inventory/SBOM reference: `<reference>`

## Component and dependency coverage

| Component/runtime/tool class | Direct or transitive | Version tracked? | Supported/maintained? | Vulnerability monitoring | Update path tested? | Owner | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `<component>` | `<direct/transitive/tool/runtime>` | `<yes/no>` | `<yes/no/unknown>` | `<source/process>` | `<yes/no>` | `<owner>` | `<reference>` |

## Supply-chain review checks

- [ ] Direct and transitive dependencies are inventoried with versions where technically feasible.
- [ ] Operating systems, runtimes, application servers, databases, libraries, client-side components, build tools, and other material software dependencies are included rather than reviewing only application libraries.
- [ ] Unsupported, unmaintained, obsolete, or out-of-date components are identified and assigned a disposition.
- [ ] Vulnerability/security-advisory monitoring covers the component sources that matter to the application.
- [ ] Dependency updates and security fixes can be tested and deployed through an owned process.
- [ ] Build, package, distribution, and update paths are reviewed for unauthorized or malicious modification risk.
- [ ] Dependency sources and package repositories are restricted or governed according to the organization’s software-supply-chain policy.
- [ ] Generated artifacts can be traced to an approved build/release process.
- [ ] Supply-chain exceptions have owners and review/expiry dates.

## Findings and actions

- Unsupported/unmaintained components: `<references>`
- Unknown/untracked transitive dependencies: `<references>`
- Vulnerability-monitoring gaps: `<references>`
- Build/distribution integrity gaps: `<references>`
- Corrective actions/owner/date: `<text>`

## Verification

- Dependency/version reconciliation: `<reference/result>`
- Vulnerability/advisory monitoring test: `<reference/result>`
- Security update/upgrade exercise: `<reference/result>`
- Build/artifact provenance or integrity evidence: `<reference/result>`

## Source

- OWASP Top 10:2025 A03 — Software Supply Chain Failures: https://owasp.org/Top10/2025/A03_2025-Software_Supply_Chain_Failures/
