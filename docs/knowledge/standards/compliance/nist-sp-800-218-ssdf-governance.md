---
title: "NIST SP 800-218 Secure Software Development Framework"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# NIST SP 800-218 Secure Software Development Framework

## Publication and scope

This article operationalizes **NIST Special Publication 800-218, Secure Software Development Framework Version 1.1: Recommendations for Mitigating the Risk of Software Vulnerabilities**. It describes governance evidence and decisions; it does not make the publication mandatory or claim certification. Applicability depends on the organization, system, contract, and legal context.

## SSDF practices and task identifiers

SSDF 1.1 groups practices under Prepare the Organization (PO), Protect the Software (PS), Produce Well-Secured Software (PW), and Respond to Vulnerabilities (RV). Named practices include PO.1 Define Security Requirements, PO.3 Implement Supporting Toolchains, PO.5 Implement and Maintain Secure Environments; PS.1 Protect All Forms of Code, PS.2 Provide a Mechanism for Verifying Software Release Integrity, PS.3 Archive and Protect Each Software Release; PW.1 Design Software to Meet Security Requirements, PW.4 Reuse Existing Well-Secured Software, PW.7 Review and/or Analyze Human-Readable Code, PW.8 Test Executable Code, PW.9 Configure Software Securely; RV.1 Identify and Confirm Vulnerabilities, RV.2 Assess, Prioritize, and Remediate, and RV.3 Analyze Vulnerabilities to Identify Root Causes.

## Publication-specific workflow

Map applicable practices and tasks to lifecycle gates and owners; define security requirements; secure repositories, build systems, and credentials; retain release integrity data; perform threat modeling, review, and executable testing; manage third-party components; publish vulnerability intake; remediate and analyze root causes; feed lessons into PO and PW tasks.

Assign named owners for each decision and define review triggers. Tailor implementation to mission impact and architecture, but preserve the publication's named concepts so reviewers can trace local practice back to the source. Document assumptions, exclusions, inherited capabilities, and residual risk rather than presenting partial coverage as full implementation.

## Evidence to retain

Keep the SSDF practice/task mapping, role assignments, requirements, threat models, repository controls, build provenance, review and test output, dependency decisions, release attestation and archive, vulnerability intake, remediation SLA, root-cause analysis, and process corrections.

Evidence must identify scope, collection date, source, owner, and covered population. Preserve raw results separately from interpretation. When remediation occurs, retain the original finding and append verification rather than rewriting history.

## Review and metrics

Review after material system, supplier, threat, mission, or organizational changes and at the stated document cycle. Metrics must include denominators and blind spots. Track overdue high-impact decisions, evidence age, exceptions approaching expiry, failed tests, and time to verified closure. Management review should focus on consequences and unresolved risk, not a context-free completion percentage.

## Failure modes

Do not claim SSDF adoption from a scanner, omit task-level mappings, protect source while leaving builds mutable, archive releases without integrity data, treat third-party code as out of scope, or close vulnerabilities without root-cause feedback.

Also avoid unsupported claims based only on policy text, a product purchase, or one convenience sample. If evidence is unavailable, record the unknown, affected scope, interim safeguard, accountable owner, and decision deadline.

## Primary Sources

- [NIST Special Publication 800-218, Secure Software Development Framework Version 1.1: Recommendations for Mitigating the Risk of Software Vulnerabilities](https://csrc.nist.gov/pubs/sp/800/218/final)
