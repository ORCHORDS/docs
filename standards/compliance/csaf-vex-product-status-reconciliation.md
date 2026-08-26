# CSAF VEX product-status reconciliation

**Issue:** A machine-readable advisory marks one product not affected while consumers apply that status to related but different versions.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Pin CSAF 2.0/profile and validate schema/profile. Resolve product-tree relationships to exact installed products. Preserve issuer, revision history, distribution, vulnerability, product status, justification, remediation, and flags. Reject contradictory status buckets. Reconcile newer revisions and withdrawn/superseded advisories without deleting decision history.

## Verification

Use fixtures for sibling versions, product groups, multiple vulnerabilities, invalid IDs, conflicting statuses, and amended remediation. Compare consumer matches with publisher examples.

## Gotchas

A VEX profile is an assertion, not proof. Product identity errors are more dangerous than parser errors. Do not treat `known_not_affected` as inherited by all descendants.

## Sources

- [OASIS CSAF 2.0 specification](https://docs.oasis-open.org/csaf/csaf/v2.0/csaf-v2.0.html)
- [CISA SBOM/VEX resources](https://www.cisa.gov/topics/cyber-threats-and-advisories/sbom/sbomresourceslibrary)
