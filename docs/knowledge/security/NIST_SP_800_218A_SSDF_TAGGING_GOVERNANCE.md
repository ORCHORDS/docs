# NIST SP 800-218A SSDF Tagging Governance

## Purpose
Establish the governance pattern for tagging software artefacts with Secure Software Development Framework (SSDF) practice identifiers using NIST SP 800-218A so that assurance claims are traceable from production code back to practice implementation.

## Scope
Applies to every software artefact produced by the studio — source files, build configurations, container images, software bill of materials, signed attestations, and release notes — that is intended for distribution to a customer.

## Workflow
1. Maintain the SSDF practice mapping in a single version-controlled document that lists each SP 800-218 practice identifier (PO.1.1, PS.1.1, PW.1.1, etc.), its description, and the artefact type it applies to.
3. Tag each artefact at creation with the practice identifier(s) implemented by its presence; tags are encoded in metadata, commit messages, or attestation records.
5. Validate tag coverage by automated scanner that flags any released artefact missing a tag.
7. Quarterly: review the tag-to-practice mapping against updated SSDF practice descriptions and reorganise as needed.
9. For each release, generate an SSDF coverage summary listing practices implemented, practices not implemented, and the rationale for omissions.

## Controls and evidence
- Tag-to-practice mapping document with version, owner, and review date.
- Tag coverage report showing percentage of artefacts tagged, practice-level breakdown, and gaps.
- Quarterly review minutes capturing decisions and changes to mappings.
- SSDF coverage summary attached to every release with the same version as the release tag.

## Validation
- Run the tag-coverage scanner against the most recent release and confirm zero untagged artefacts.
- Recompute the practice coverage summary and reconcile with the previous release; investigate any drop in coverage.
- Sample-audit five artefacts, confirm the tag matches the practice implemented by the artefact.

## Failure correction
- **Untagged artefact in a release** → block the release, tag the artefact, document the omission cause, and re-run the validation.
- **Tag-to-practice mapping out of date** → refresh the mapping within 30 days and document the staleness window.
- **Practice coverage drops between releases** → escalate to the release manager and produce a remediation plan.

## Limitations
- SSDF tagging is one form of secure-development attestation; it is complementary to, not a replacement for, SLSA provenance or Sigstore signing.
- Practice identifier lists may evolve; keep mapping documents aligned with the latest published version of SP 800-218 and SP 800-218A.
- Tagging alone does not validate that the practice is implemented effectively — manual review and evidence inspection are still necessary.

## Scope note
This article is part of the security leaf. Cross-reference: NIST_SP_800_161_R1_C_SCRM_PROGRAM_GOVERNANCE.md, NIST_IR_8441_CYBERSUPPLY_CHAIN_RISK_GOVERNANCE.md, NIST_SP_800_61_R3_INCIDENT_LEGAL_COORDINATION_GOVERNANCE.md.

## Canonical sources
- NIST SP 800-218 (SSDF v1.1): https://csrc.nist.gov/pubs/sp/800/218/final
- NIST SP 800-218A (SSDF profile tagging): https://csrc.nist.gov/pubs/sp/800/218/a/final
- NIST SP 800-53 Rev. 5 control catalogue: https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- NIST SP 800-161r1 (Cybersecurity Supply Chain Risk Management Practices): https://csrc.nist.gov/pubs/sp/800/161/r1/final
- NIST SSDF Community Profiles working group: https://csrc.nist.gov/projects/ssdf