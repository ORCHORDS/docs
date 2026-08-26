# CISA SSVC decision record

**Issue:** Vulnerability priorities are assigned from severity alone without recording exploitation, technical impact, mission prevalence, and stakeholder decision context.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Use CISA Stakeholder-Specific Vulnerability Categorization as a transparent decision aid, not an automated risk score.

## Controls

Record SSVC version/tree, stakeholder role, evidence for each decision point, resulting action, analyst, timestamp, asset scope, and reevaluation triggers. Keep CVSS, KEV, EPSS, business impact, exposure, and compensating controls as separate evidence. Require review for overrides.

## Verification

Have independent analysts classify fixtures and reconcile disagreement; replay decisions when exploitation or exposure changes; audit action outcomes and missed incidents.

## Gotchas

Decision trees differ by stakeholder. Unknown evidence must not be silently treated as favorable. SSVC prioritization does not establish vulnerability presence.

## Sources

- [CISA Stakeholder-Specific Vulnerability Categorization](https://www.cisa.gov/stakeholder-specific-vulnerability-categorization-ssvc)
