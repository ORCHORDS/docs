# CVSS v4 Threat and Environmental score reassessment

**Issue:** Teams copy a vendor CVSS Base score into a permanent priority without adding current exploit maturity, local safety/impact, security requirements, or compensating controls.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Preserve the authoritative CVSS v4 Base vector, then let the consumer calculate and label Threat and Environmental enrichment. FIRST nomenclature distinguishes CVSS-B, CVSS-BT, CVSS-BE, and CVSS-BTE.

## Issue record

Store source vector, source/date, local vector, nomenclature, score date, analyst, asset scope, threat evidence, environmental rationale, compensating controls, and next review trigger.

## Flow

1. Select the Base assessment most relevant to the deployed product.
2. Validate vector syntax and do not infer omitted Base metrics.
3. Apply Threat Exploit Maturity using current evidence.
4. Apply Environmental metrics for local modified metrics and security requirements.
5. Use Supplemental metrics as context, not hidden score manipulation.
6. Recalculate after exploit, architecture, exposure, or control changes.
7. Combine with KEV/EPSS, asset criticality, and remediation feasibility.

## Verification

Use FIRST's reference calculator/test vectors, require two-person review for high-impact overrides, and backtest local priorities. Display probability signals separately from CVSS severity.

## Gotchas

Not Defined uses specification defaults; it is not “zero.” Vendors should generally publish Base, while consumers own local Threat/Environmental metrics. A lower local score does not erase mandatory remediation.

## Sources

- [FIRST CVSS v4.0 specification](https://www.first.org/cvss/v4.0/specification-document)
- [FIRST CVSS v4.0 User Guide](https://www.first.org/cvss/v4.0/user-guide)
- [FIRST CVSS v4 Consumer Implementation Guide](https://www.first.org/cvss/v4.0/implementation-guide)
