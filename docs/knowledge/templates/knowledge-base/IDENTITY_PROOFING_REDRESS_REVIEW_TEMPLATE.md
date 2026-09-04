# Identity-Proofing Redress Review Template

Use this record to review applicant redress, alternative proofing, and failure-message disclosure controls against NIST SP 800-63A-4. Do not include real applicant identity data or authoritative-source mismatch details.

## Review metadata

- Identity service: `<name>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Proofing channels in scope: `<online/in-person/etc.>`

## Redress accessibility

- Redress/help location: `<reference>`
- Applicant-facing contact channel: `<channel>`
- Alternative proofing methods available: `<summary>`
- Accessibility/language accommodations: `<summary>`

## Failure-disclosure matrix

| Failure class | Applicant message | Internal diagnostic retained? | Leaks specific mismatch? | Result |
| --- | --- | --- | --- | --- |
| Evidence validation failure | `<message>` | `<yes/no>` | `<yes/no>` | `<pass/fail>` |
| Attribute mismatch | `<message>` | `<yes/no>` | `<yes/no>` | `<pass/fail>` |
| Technical failure | `<message>` | `<yes/no>` | `<yes/no>` | `<pass/fail>` |
| User capture/process failure | `<message>` | `<yes/no>` | `<yes/no>` | `<pass/fail>` |

## Review checks

- [ ] Redress mechanisms are easy for applicants to find and access.
- [ ] Failed proofing explains how to address the problem without revealing the specific attribute/evidence mismatch.
- [ ] Detailed diagnostics are retained only in protected internal systems for authorized staff.
- [ ] UI, API, support scripts, email, and other channels apply a consistent disclosure policy.
- [ ] Alternative proofing methods are made clear when online enrollment cannot be completed.
- [ ] Staff have enough internal evidence to assist legitimate applicants without exposing fraud-enabling detail externally.

## Test evidence

- Different-attribute mismatch tests: `<reference/result>`
- API/UI disclosure comparison: `<reference/result>`
- Support-script test: `<reference/result>`
- Alternative-path discoverability test: `<reference/result>`

## Findings and actions

- Findings: `<text>`
- Corrective actions/owner/date: `<text>`
- Retest result: `<result>`

## Source

- NIST SP 800-63A-4, Privacy — Redress: https://pages.nist.gov/800-63-4/sp800-63a/privacy/
