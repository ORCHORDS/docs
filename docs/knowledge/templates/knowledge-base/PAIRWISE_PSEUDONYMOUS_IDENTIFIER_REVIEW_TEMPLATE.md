# Pairwise Pseudonymous Identifier Review Template

Use this record to review pairwise pseudonymous identifiers (PPIs) and cross-RP correlation risk against NIST SP 800-63C-4. Do not place real subscriber identifiers or secret derivation keys in this public record.

## Review metadata

- Identity provider/federation service: `<name>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- RPs in scope: `<non-sensitive list/reference>`

## PPI generation properties

| Property | Result | Evidence |
| --- | --- | --- |
| Different identifier per unrelated RP | `<pass/fail>` | `<reference>` |
| Contains no identifying information | `<pass/fail>` | `<reference>` |
| Difficult to guess / sufficient entropy | `<pass/fail>` | `<reference>` |
| Derivation irreversible/secret-key protected if derived | `<pass/fail/not applicable>` | `<reference>` |
| Mapping to upstream identifiers protected as subscriber information | `<pass/fail>` | `<reference>` |

## Shared-PPI review

- Shared PPI in use: `<yes/no>`
- RP set: `<reference>`
- Trust-agreement clause: `<reference>`
- Authorized-party notice/consent evidence: `<reference>`
- Operational relationship justifying correlation: `<summary>`
- Consent of all RPs in the shared set: `<reference>`
- Privacy-risk assessment: `<reference>`

## Review checks

- [ ] Unrelated RPs receive different PPIs for the same subscriber.
- [ ] PPI values do not embed usernames, email addresses, employee numbers, or other identifying data.
- [ ] PPI generation is not practically guessable from known subscriber information.
- [ ] A non-shared PPI is disclosed to only one RP.
- [ ] Any shared PPI is limited to the RP set defined by the trust agreement.
- [ ] An RP outside the approved shared set cannot obtain the shared PPI.
- [ ] Attribute release is reviewed separately because common identifying attributes can still enable cross-RP correlation even when PPIs differ.

## Verification evidence

- Same-subscriber/different-RP test: `<result>`
- Identifier entropy/structure review: `<result>`
- Unauthorized-RP shared-PPI test: `<result/not applicable>`
- Attribute-correlation review: `<result>`

## Findings and actions

- Findings: `<text>`
- Corrective actions/owner/date: `<text>`
- Retest result: `<result>`

## Source

- NIST SP 800-63C-4, Pairwise Pseudonymous Identifiers: https://pages.nist.gov/800-63-4/sp800-63c.html
