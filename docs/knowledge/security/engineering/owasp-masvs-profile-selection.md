---
title: "OWASP MASVS 2.1.0 Profile Selection"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# OWASP MASVS 2.1.0 Profile Selection

## Pinned source and scope
OWASP MASVS **2.1.0**. This article uses the named version and identifiers; do not combine evidence from another edition without a migration record.

## Control interpretation
MASVS 2.1.0 uses control groups MASVS-STORAGE, CRYPTO, AUTH, NETWORK, PLATFORM, CODE, RESILIENCE, and PRIVACY. Version 2 removed the old L1/L2/R verification-level structure; do not claim “MASVS L2.” Select individual controls from assets, threat actors, deployment model, regulatory duties, and whether resilience against a device owner is required.

## Domain-specific procedure
Create a control profile listing every MASVS v2.1 control ID, applicability, rationale, platform, backend dependency, MASTG tests, and evidence. Distinguish client controls from server authentication and authorization. Reassess when adding WebViews, offline secrets, new IPC surfaces, cryptographic protocols, or high-risk anti-tamper requirements.

## Evidence and decision
Retain the complete MASVS 2.1 control profile, asset/threat mapping, platform applicability, linked MASTG tests, and backend dependencies. Report selected controls, not obsolete L1/L2 labels.

## Failure modes
Copying an old level label, selecting every resilience control without a device-owner threat, or treating backend behavior as mobile-client evidence are errors.

## Sources
- [Pinned canonical source](https://github.com/OWASP/owasp-masvs/releases/tag/v2.1.0)
