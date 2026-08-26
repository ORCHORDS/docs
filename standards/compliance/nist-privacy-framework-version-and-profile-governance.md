# NIST Privacy Framework version and profile governance

**Issue:** Privacy controls drift when teams mix identifiers and guidance from NIST Privacy Framework 1.0 with the 1.1 initial public draft, or treat a voluntary framework as a binding legal requirement.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Pin every organizational privacy profile to an identified NIST Privacy Framework publication status. NIST's public materials still identify Version 1.0 as the published framework and Version 1.1 as an initial public draft whose comment period closed in 2025; do not label draft mappings as final.

The framework is a voluntary enterprise-risk tool and does not itself establish legal compliance.

## Controls

- Maintain a Current Profile describing present outcomes and a Target Profile describing prioritized improvement.
- Record framework version, publication status, approval date, owner, and applicable products.
- Map privacy risks, data processing, affected individuals, controls, metrics, and evidence to stable internal identifiers before mapping external subcategories.
- Keep a versioned crosswalk between 1.0 and draft 1.1; isolate draft-only outcomes.
- Evaluate draft changes in a sandbox governance branch and approve migration only after final publication and gap review.
- Link legal obligations separately with jurisdiction, applicability decision, and counsel-approved interpretation.

## Verification

1. Sample controls and trace internal requirement, framework mapping, implementation, and evidence.
2. Detect mixed-version identifiers in policy-as-code.
3. Review profile scope after new data uses, AI features, vendors, or jurisdictions.
4. Re-run the crosswalk when NIST publishes a final update.
5. Confirm reports say “aligned to” rather than claiming certification.

## Gotchas

Framework alignment is not proof that processing is lawful. Draft content can change. Cybersecurity risk and privacy risk overlap but are not interchangeable.

## Sources

- [NIST Privacy Framework](https://www.nist.gov/privacy-framework)
- [NIST Privacy Framework Version 1.0](https://www.nist.gov/privacy-framework/privacy-framework)
- [NIST Privacy Framework 1.1 initial public draft announcement](https://www.nist.gov/news-events/news/2025/04/nist-privacy-framework-11-initial-public-draft-available-comment)
