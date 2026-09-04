# NIST IAL2 Non-Biometric Pathway Review Template

Use this record to assess a NIST SP 800-63A-4 IAL2 Non-Biometric Pathway. This template distinguishes the absence of automated biometric comparison from the possible use of manual visual comparison of biometric identity evidence.

## Review metadata

- Identity service: `<name>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Proofing type: `<remote unattended/remote attended/on-site/etc.>`
- Relying parties using the identity service: `<non-sensitive list/reference>`

## Evidence and verification mapping

| Evidence class | Evidence type | Ownership-verification method | Automated biometric comparison used? | Evidence |
| --- | --- | --- | --- | --- |
| `<FAIR/STRONG/SUPERIOR>` | `<type>` | `<confirmation code/visual comparison/etc.>` | `<yes/no>` | `<reference>` |

## Pathway checks

- [ ] The pathway does not depend on automated comparison of biometric samples.
- [ ] Each presented evidence item is verified according to the ownership requirements applicable to its evidence class and proofing type.
- [ ] Manual visual comparison is documented accurately as manual rather than described as “non-biometric data processing” if biometric data is still involved.
- [ ] The subscriber record captures the verification method where NIST requires it, including mailed confirmation-code or visual-comparison use.
- [ ] Relying parties are informed when the CSP offers/uses the IAL2 Non-Biometric Pathway as required by NIST.
- [ ] Alternative/fallback steps do not silently reduce the achieved IAL below the claimed level.

## Verification evidence

- Representative end-to-end non-biometric pathway test: `<result>`
- Confirmation-code ownership-verification test: `<result/not applicable>`
- Manual visual-comparison test: `<result/not applicable>`
- Subscriber-record evidence: `<reference>`
- RP communication evidence: `<reference>`

## Findings and actions

- Findings: `<text>`
- Corrective actions/owner/date: `<text>`
- Retest result: `<result>`

## Source

- NIST SP 800-63A-4, IAL2 Verification — Non-Biometric Pathway: https://pages.nist.gov/800-63-4/sp800-63a/ial/
