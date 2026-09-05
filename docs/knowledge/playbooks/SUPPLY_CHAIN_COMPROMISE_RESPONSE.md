---
title: "Software Supply Chain Compromise Response Playbook"
owner: "Application Security Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-09-04"
review-cycle: "90 days"
next-review: "2026-12-03"
---

# Software Supply Chain Compromise Response Playbook

## Trigger

Use this playbook when a software dependency, build tool, registry, signing identity, distribution channel, or supplier is suspected or confirmed to be compromised, or when a known compromise (CVE, vendor advisory, intelligence feed) requires coordinated response across the organization.

## Scope

Apply the process to direct dependencies (libraries, packages, frameworks), transitive dependencies, build tools and infrastructure, container base images, signed artifacts, internal artifact registries, and supplier and vendor trust relationships.

## Inputs

- advisory identifier (CVE, GHSA, vendor advisory) and affected component;
- SBOM showing presence of the affected component in in-scope systems;
- provenance attestations and signature verification status;
- supplier trust record and contractual obligations;
- detection indicators (artifact hash, suspicious behavior, IOCs).

## Steps

1. **Triage the advisory.** Determine whether the advisory applies to in-scope systems; assess exploitability, impact, and reachability from the SBOM and runtime traces.
2. **Contain access.** Restrict or revoke access to the compromised component, artifact, or identity; disable automated pulls; rotate downstream credentials that trust the compromised identity.
3. **Preserve evidence.** Capture hashes, signatures, and timestamps of compromised artifacts; snapshot registry state; retain audit logs from the build and distribution path.
4. **Notify supply chain stakeholders.** Engage the supplier, the maintainer, and downstream consumers; route communications through authorized channels.
5. **Identify affected artifacts.** Use the SBOM and provenance data to enumerate every build that consumed the compromised component; produce a complete inventory.
6. **Revert or patch.** Replace the affected component with a known-clean version where possible; for unrecoverable cases, patch or apply a documented mitigation; document the rationale for the chosen approach.
7. **Rebuild and re-sign.** From a known-clean source, rebuild affected artifacts; regenerate signatures; update SBOMs and attestations; revoke old signatures.
8. **Verify integrity at deploy.** Validate signatures, hashes, and attestations at promotion; reject artifacts that fail verification.
9. **Communicate.** Coordinate internal, customer, supplier, and regulator notifications through the documented incident communications process.
10. **Close and learn.** Document root cause, decisions, timeline, and corrective actions; update supplier security requirements; tighten build provenance and signature enforcement.

## Escalation

Escalate to the Application Security Lead, Engineering Owner, Legal, and Executive leadership when:
- a build or signing identity is compromised;
- the compromise extends across multiple suppliers or products;
- an active exploit against the organization is observed;
- the compromise affects customer data or critical infrastructure.

## Evidence

- advisory identifiers and reachability mapping;
- SBOM and provenance data showing exposure;
- build, registry, and signing audit logs;
- re-build and re-sign records;
- communications artifacts and notification records.

## Completion Criteria

The response is considered complete when:
- all affected artifacts are identified, contained, and rebuilt where applicable;
- signatures and attestations are updated and validated;
- customers and regulators are notified where required;
- supplier and build-pipeline controls are updated to prevent recurrence.

## Exceptions

Document deviations with the approver, scope, expiration, compensating control, and review schedule. Where a vendor mitigation is not available, document the compensating controls and the timeline for resolution.

## Related Documents

- [SLSA Build Level 3 Governance](../reference/SLSA_BUILD_LEVEL_3_GOVERNANCE.md)
- [NIST SP 800-218A SSDF Profile](NIST_SP_800_218A_GENAI_PROFILE_VERSION_GUIDE.md)
- [NIST SP 800-161 Cybersecurity Supply Chain Risk Management](NIST_SP_800_161_C_SCRM.md)
- [CNCF Software Supply Chain Best Practices](CNCF_SUPPLY_CHAIN_BEST_PRACTICES.md)
