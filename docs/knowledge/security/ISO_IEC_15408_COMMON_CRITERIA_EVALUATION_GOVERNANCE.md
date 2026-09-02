# ISO/IEC 15408 Common Criteria Evaluation Governance

## Purpose

Govern the studio's engagement with ISO/IEC 15408 (the Common Criteria) so that evaluation of security-relevant products — whether the studio's product entering evaluation or evaluation evidence the studio consumes as a buyer — proceeds correctly: protection profile alignment, evaluation assurance level selection, and correct reliance on Common Criteria certificates.

## Scope

Applies to Common Criteria evaluation activity involving the studio: commissioning evaluations of studio products and relying on others' certificates in procurement. Covers EAL selection, protection profile usage, and certificate reliance. Does not cover the general ISMS or product security development.

## Workflow

1. Determine evaluation need from market or regulatory requirements: which customers or regimes demand Common Criteria certification and against which protection profiles; evaluation without a relying party is cost without purpose.
2. Select the protection profile where one exists for the product class (operating systems, secure elements, network devices have established profiles); profile conformance constrains the security target and simplifies buyer reliance.
3. Write or align the security target (ST): the ST is the evaluation's contract — the product's security problem definition, objectives, and the security functional requirements claimed; vague STs produce vague evaluations.
4. Select the evaluation assurance level (EAL) deliberately: EAL2 through EAL7 trade evaluation depth for cost; the relying parties' requirements usually dictate the level — exceed them only with a commercial reason.
5. Engage a licensed laboratory operating in the CCRA (Common Criteria Recognition Arrangement): the certificate's recognition scope depends on the arrangement's mutual recognition and any national caveats.
6. Maintain through the lifecycle: certificates carry assurance maintenance or re-evaluation obligations when the product changes; shipping uncertified major versions breaks the certificate's coverage claim.
7. As a buyer, read certificates precisely: profile conformance, EAL, version scope, and recognition caveats — an EAL2 certificate for a different product version is not assurance for what you deploy.

## Controls and evidence

- Evaluation need determination with relying parties named.
- Security target with problem definition and requirements trace.
- EAL selection rationale.
- Laboratory engagement and certificate records.
- Assurance maintenance records for product changes.
- Certificate reliance notes for procurement decisions.

## Validation

- Confirm the current certificate covers the shipped product version (or maintenance evidence does).
- Confirm the ST's claims match the product's actual security functionality.
- Sample buyer-side reliance decisions: confirm each checked profile conformance and version scope.

## Failure correction

- **Product version out of certificate scope** → trigger assurance maintenance or re-evaluation; uncertified shipping to relying customers is a contract matter.
- **ST claims drifting from product** → correct the ST or product through evaluation change control; drift found at evaluation becomes findings.
- **Buyer over-reliance (ignoring caveats/version)** → annotate the certificate record with scope limits and re-review the procurement decision.

## Limitations

- Common Criteria evaluates at a point in time against the ST's claims; it is not a vulnerability warranty or a substitute for ongoing product security.
- Evaluation cycles are long; agile product cadences strain the assurance maintenance model.
- CCRA recognition has participant and caveat limits; certificates do not travel universally.

## Scope note

This article is part of the security leaf. Cross-reference: `FIPS_140_3_CRYPTOGRAPHIC_MODULE_VALIDATION_GOVERNANCE.md`, `ISO_IEC_19790_SECURITY_TECHNIQUES_EVALUATION_GOVERNANCE.md`, and `NIST_SP_800_53B_CONTROL_BASELINES_OVERLAYS_GOVERNANCE.md`.

## Canonical sources

- ISO/IEC 15408-1:2022 — Evaluation criteria for IT security — Introduction and general model: https://www.iso.org/obp/ui/#iso:std:iso-iec:15408:-1
- ISO/IEC 15408-2:2022 — Security functional components: https://www.iso.org/obp/ui/#iso:std:iso-iec:15408:-2
- ISO/IEC 15408-3:2022 — Security assurance components: https://www.iso.org/obp/ui/#iso:std:iso-iec:15408:-3
- Common Criteria Portal — Recognized profiles and certificates: https://www.commoncriteriaportal.org/
- Common Criteria Recognition Arrangement: https://www.commoncriteriaportal.org/ccra/
