# NIST C-SCRM supplier criticality assessment

**Issue:** Every supplier receives the same diligence even though compromise, substitution, or outage would have radically different effects.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Use NIST SP 800-161r1 Update 1 as the publication baseline. Inventory products/services, data and privilege, deployment reach, substitutability, concentration, transitive suppliers, update channels, and recovery dependence. Assign criticality before selecting diligence depth. Require stronger provenance, incident notice, continuity, vulnerability, termination, and evidence terms for critical suppliers.

## Verification

Trace a critical service through dependencies and recovery; test supplier loss/substitution; sample risk ratings against actual access and deployment.

## Gotchas

Spend is not criticality. A small build plugin may have organization-wide reach. Certifications do not replace product-specific risk assessment.

## Sources

- [NIST SP 800-161r1 Update 1](https://csrc.nist.gov/pubs/sp/800/161/r1/upd1/final)
- [NIST C-SCRM project](https://csrc.nist.gov/Projects/cyber-supply-chain-risk-management)
