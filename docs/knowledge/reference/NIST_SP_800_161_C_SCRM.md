---
title: "NIST SP 800-161 Cybersecurity Supply Chain Risk Management"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-161 Rev. 1 (May 2022, with updates); https://csrc.nist.gov/publications/detail/sp/800-161/rev-1/final"
---

# NIST SP 800-161 Cybersecurity Supply Chain Risk Management

## Scope

Reference card for NIST Special Publication 800-161 Revision 1, *Cybersecurity Supply Chain Risk Management Practices for Systems and Organizations* (May 2022, with subsequent updates including C-SCRM overlays). The publication is the canonical reference for C-SCRM controls and practices in the US federal sector and a recognized baseline for private-sector profiles. Profiles that govern supply-chain risk should reference SP 800-161 Rev. 1 by version and bind it to NIST SSDF (SP 800-218), SLSA, the CNCF best practices, and the FedRAMP supply-chain guidance.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | NIST SP 800-161 Rev. 1 (May 2022, with updates) |
| Status | Final; current edition |
| Supersedes | SP 800-161 Rev. 1 (initial publication, 2019); SP 800-161 (original, 2015) |
| Companion artifacts | NIST SSDF (SP 800-218), SLSA, NIST CSF, FedRAMP supply-chain guidance, ISO/IEC 27036 |
| Source URL | https://csrc.nist.gov/publications/detail/sp/800-161/rev-1/final |

## Plan

1. Reference SP 800-161 Rev. 1 by version whenever a profile governs C-SCRM.
2. Establish the C-SCRM governance: roles, responsibilities, risk-appetite, supplier-tier definitions, and the relationship to enterprise risk management (ISO 31000, NIST CSF).
3. Identify the supplier inventory: tier, criticality, contract controls, attestations, SBOMs, and the review cadence.
4. Apply the C-SCRM controls across the supplier lifecycle: acquisition, development, deployment, operation, retirement.
5. Apply the C-SCRM controls across the software, hardware, and services supply chains.
6. Bind to NIST SSDF (SP 800-218) for in-house development and to SLSA / CNCF best practices for the cloud-native supply chain.
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- SP 800-161 Rev. 1 normative sections: 2 (C-SCRM fundamentals), 3 (C-SCRM controls), 4 (C-SCRM practices), appendices.
- Internal supplier inventory, contract clauses, attestations, SBOMs.
- Procurement policy and supplier-risk policy.
- NIST SSDF (SP 800-218) and SLSA frameworks.

## ORCHORDS Profile

ORCHORDS treats SP 800-161 Rev. 1 as the canonical reference for C-SCRM. Profiles that reference C-SCRM should cite the version, identify the controls adopted, and bind to NIST SSDF, SLSA, and the CNCF best practices.

A profile that references "supply chain risk management" without binding to a recognized framework is non-conformant.

## Implementation Notes

- C-SCRM is a continuous programme, not a one-time assessment; supplier review should be periodic, not one-off.
- Supplier-tier definitions drive the depth of review; tier-1 (direct) suppliers warrant more review than tier-2 and beyond.
- SBOMs (SPDX, CycloneDX) are inputs to vulnerability management; they are not a substitute for vulnerability scanning.
- Software and hardware supply chains have different risk profiles; apply the relevant C-SCRM controls for each.
- C-SCRM should be integrated with the broader enterprise risk-management framework rather than managed as a separate compliance function.

## Companion Documents

- [NIST SSDF SP 800-218 Secure Software Development Framework](NIST_SSDF_SP_800_218.md)
- [Supply Chain Levels for Software Artifacts (SLSA)](SUPPLY_CHAIN_LEVELS_SOFTWARE_ARTIFACTS.md)
- [SLSA Build Level 3 Governance](SLSA_BUILD_LEVEL_3_GOVERNANCE.md)
- [CNCF Supply Chain Best Practices](CNCF_SUPPLY_CHAIN_BEST_PRACTICES.md)
- NIST SP 800-218A GenAI Profile Version Guide
- [Container Image Build Hardening Response](../playbooks/CONTAINER_IMAGE_BUILD_HARDENING_RESPONSE.md)
- [Supply Chain Compromise Response](../playbooks/SUPPLY_CHAIN_COMPROMISE_RESPONSE.md)
