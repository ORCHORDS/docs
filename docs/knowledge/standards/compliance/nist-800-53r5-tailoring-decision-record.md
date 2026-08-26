# NIST SP 800-53r5 tailoring decision record

**Issue:** Baseline controls are removed or altered without preserving the scoping, parameter, compensating-control, and risk decisions that produced the tailored baseline.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Freeze publication/revision and source baseline. For every tailoring action record control/enhancement, action, rationale, system scope, risk owner, organization-defined parameter, compensating control, dependency, approval, and review trigger. Keep common-control inheritance separate from exclusions. Map the result to implementation and assessment objectives.

## Verification

Regenerate the tailored catalog from the record; trace samples to deployed controls and assessment evidence; detect undefined parameters and orphaned compensating controls; review after boundary, threat, mission, or regulation changes.

## Gotchas

Tailoring is not deleting inconvenient controls. Applicability, inheritance, and satisfaction are different states. This is governance guidance, not a claim that SP 800-53 is contractually applicable.

## Sources

- [NIST SP 800-53 Rev. 5 Update 1](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)
- [NIST tailoring glossary definition](https://csrc.nist.gov/glossary/term/tailoring)
