# DORA ICT third-party register of information

**Issue:** An in-scope financial entity has supplier records but cannot produce a complete, consistent register of ICT service dependencies and subcontractors that support critical or important functions.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

## Scope

This is for financial entities in scope of the EU Digital Operational Resilience Act (DORA), not a universal SaaS requirement. DORA applies from 17 January 2025. The implementing technical standard defines structured register-of-information templates.

**Sources:**

- [Regulation (EU) 2022/2554 — DORA](https://eur-lex.europa.eu/eli/reg/2022/2554/oj/eng)
- [Commission Implementing Regulation (EU) 2024/2956](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202402956)

## Operating model

Maintain a controlled supplier/dependency inventory that links:

- each ICT service and contract to the legal provider;
- direct services and material subcontractors;
- the supported business function and whether it is critical or important;
- service location, data/service dependencies, renewal/exit terms, and responsible owner;
- evidence of periodic completeness, consistency, integrity, and corrective review.

Make procurement, architecture, security, legal, resilience, and vendor management jointly responsible for lifecycle updates. A spreadsheet with unknown ownership is not a defensible register.

## Verification

- a sample critical business function traces through every required direct ICT provider and relevant subcontractor;
- a terminated supplier is removed or marked historically, with evidence retained as policy requires;
- contract change, incident, and annual supplier-review workflows update the register;
- validation detects missing owners, duplicate provider identities, stale contracts, and unclassified criticality;
- reporting uses the applicable Annex templates and current supervisory instructions.

## Gotchas

- The register is broader than a security tool inventory and narrower than every business supplier list.
- Do not infer subcontractor coverage from a provider’s marketing page; obtain contractual or due-diligence evidence.
- DORA’s scope and reporting obligations require qualified legal/compliance interpretation for the entity’s jurisdiction and status.

## Related

- `compliance/dora-ict-risk-assessment-deep-dive-2026.md`
- `compliance/eu-dora-ict-third-party-register-and-incident-evidence.md`
- `security/third-party-risk-management.md`
