# NIST SSDF Security Decision Traceability Review Template

Use this evidence record to operationalize NIST SSDF v1.1 task PW.1.2 on tracking software security requirements, risks, and design decisions throughout the software life cycle.

## Review metadata

- Product/component: `<scope>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Requirements/risk/design repositories: `<references>`
- Release/milestone: `<reference>`

## Traceability sample

| Security requirement or risk | Source | Design/implementation decision | Risk response / mitigation | Exception? | Verification evidence | Owner | Current status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `<requirement/risk>` | `<source>` | `<decision>` | `<response>` | `<yes/no>` | `<reference>` | `<owner>` | `<status>` |

## Review checks

- [ ] Security requirements applicable to the software are recorded in a maintained system rather than existing only in informal conversation.
- [ ] Material security risks identified during design/development are linked to an explicit response, mitigation, acceptance, transfer, avoidance, or other approved disposition.
- [ ] Security-relevant design decisions record enough rationale for later maintenance and review.
- [ ] Approved exceptions to security requirements have accountable owners and rationale.
- [ ] Mitigations introduced in response to identified risks are reflected back into requirements, design, implementation, or verification work as appropriate.
- [ ] Security requirements and risk decisions are traceable to verification/test evidence before release where required by the organization’s SDLC.
- [ ] Material changes in architecture, threat model, dependencies, or business context trigger review of affected requirements and prior decisions.
- [ ] Exceptions and accepted risks are periodically reconsidered rather than treated as permanent by default.
- [ ] Records remain accessible for maintenance, audit, incident investigation, and future design changes over the required product life cycle.

## Verification exercise

- Sample security requirement: `<reference>`
- Linked risk/design decision: `<reference>`
- Linked implementation/mitigation: `<reference>`
- Linked verification evidence: `<reference>`
- Exception/review evidence if applicable: `<reference>`
- Traceability result: `<complete/partial/missing>`

## Findings and actions

- Untracked security requirements: `<text>`
- Risks without explicit disposition: `<text>`
- Design decisions without rationale: `<text>`
- Stale exceptions/accepted risks: `<text>`
- Corrective actions/owner/date: `<text>`

## Sources

- NIST SP 800-218, Secure Software Development Framework (SSDF) Version 1.1: https://csrc.nist.gov/pubs/sp/800/218/final
- NIST SSDF project page — v1.1 addition PW.1.2: https://csrc.nist.gov/projects/ssdf
