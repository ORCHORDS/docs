---
title: "NIST SSDF SP 800-218 Secure Software Development Framework"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-218 v1.1 (February 2022); https://csrc.nist.gov/publications/detail/sp/800-218/final"
---

# NIST SSDF SP 800-218 Secure Software Development Framework

## Scope

Reference card for NIST Special Publication 800-218 Version 1.1, *Secure Software Development Framework (SSDF) Version 1.1* (February 2022). Used by software, platform, and supply-chain teams when documenting secure-development practices, internal control catalogs, supplier attestations, or procurement language that requires an SSDF-aligned practice set. Treats SP 800-218 v1.1 as the current normative artifact; the 2022 revision replaced SP 800-218 v1.0 (September 2020) without removing practices.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | NIST SP 800-218 v1.1, *Secure Software Development Framework (SSDF) v1.1* |
| Status | Final (February 2022) |
| Supersedes | SP 800-218 v1.0 (September 2020) |
| Companion artifacts | SP 800-218A (GenAI profile), SSDF community profiles, OWASP SAMM, BSIMM |
| Practice families | PO (Prepare the Organization), PS (Protect the Software), PW (Produce Well-Secured Software), RV (Respond to Vulnerabilities) |
| Source URL | https://csrc.nist.gov/publications/detail/sp/800-218/final |

## Plan

1. Reference SSDF v1.1 by version, practice family, and practice identifier whenever a profile describes secure-development expectations for in-house or supplied software.
2. Map existing engineering controls to the four practice families (PO, PS, PW, RV) and the practices under each family.
3. Treat SSDF practice statements as the binding language; organizational or supplier-specific controls should be expressed as implementations of the SSDF practice rather than as parallel frameworks.
4. When SSDF is required as a procurement or attestation clause, bind the clause to specific practice identifiers so the requirement is verifiable.
5. Track SSDF profile drift: any community profile, supplier attestation, or GenAI overlay (SP 800-218A) should be tracked separately and identified by its publication date.

## Inputs

- SP 800-218 v1.1 practice statements with their identifier, family, and the explanatory text that follows each practice.
- Internal secure-development procedures, code-review standards, threat-modeling procedures, dependency-management policies, vulnerability-handling procedures.
- Supplier-provided secure-development attestations, SBOMs, and accompanying SLSA or supply-chain evidence.
- Vulnerability disclosures, internal red-team findings, and post-incident corrective actions.

## ORCHORDS Profile

ORCHORDS treats SSDF v1.1 as the canonical reference for secure-development control language. Profiles in `docs/knowledge/standards/`, `docs/knowledge/playbooks/`, and `docs/knowledge/reference/` that reference SSDF should use the v1.1 practice identifier and family notation. References that pre-date v1.1 should be flagged for re-ratification rather than silently carried forward.

Where a profile extends SSDF with a GenAI overlay, that overlay is governed by SP 800-218A rather than SP 800-218 v1.1 directly. Where a profile depends on a community or sector profile (for example the Canadian ITSG-33 or the US Government SSDF profile), the binding should name the profile and version, not just "SSDF".

## Implementation Notes

- Practice statements are normative; examples and informative annexes are not. Profile authors should not paraphrase practice statements in ways that weaken the binding.
- The four families (PO, PS, PW, RV) are not lifecycle phases. Profiles that treat them as sequential phases misapply the framework.
- Vulnerability response (RV) should be connected to internal incident-response playbooks and external coordinated-disclosure procedures rather than managed as a developer-only function.
- Supplier attestations should be retained with the practice identifier list and the attestation date; a renewal cadence should be defined in the supplier-management policy.
- Internal development environments are part of the SSDF scope. PO practices cover the development environment itself, including access control, hardening, and integrity of the toolchain.

## Companion Documents

- NIST SP 800-218A GenAI Profile Version Guide
- NIST SP 800-218A GenAI Profile Version Governance
- [Supply Chain Levels for Software Artifacts (SLSA)](SUPPLY_CHAIN_LEVELS_SOFTWARE_ARTIFACTS.md)
- [CNCF Supply Chain Best Practices](CNCF_SUPPLY_CHAIN_BEST_PRACTICES.md)
- [NIST SP 800-161 C-SCRM](NIST_SP_800_161_C_SCRM.md)
- [NIST SP 800-53 Rev. 5 Access Control Family](NIST_SP_800_53_REV_5_ACCESS_CONTROL_FAMILY.md)
- [NIST SP 800-52 TLS Guidelines](NIST_SP_800_52_TLS_GUIDELINES.md)
