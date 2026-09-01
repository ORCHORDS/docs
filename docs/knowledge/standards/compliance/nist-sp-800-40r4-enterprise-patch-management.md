---
title: "NIST SP 800-40 Rev. 4 Enterprise Patch Management"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# NIST SP 800-40 Rev. 4 Enterprise Patch Management

## Publication and scope

This article operationalizes **NIST Special Publication 800-40 Revision 4, Guide to Enterprise Patch Management Planning: Preventive Maintenance for an Organization’s Technology**. It describes governance evidence and decisions; it does not make the publication mandatory or claim certification. Applicability depends on the organization, system, contract, and legal context.

## Preventive maintenance and risk response

SP 800-40r4 treats enterprise patch management as preventive maintenance and a form of risk response, not merely an IT deployment queue. It defines organizational strategy, technology inventory, risk-based prioritization, acquisition and validation of patches, deployment, verification, exception handling, and performance improvement. It distinguishes routine patching from emergency response.

## Publication-specific workflow

Establish maintenance groups and maintenance windows; maintain authoritative inventories; receive vendor information through trusted channels; determine applicability and risk; test representative configurations; approve and deploy in waves; monitor failures and rollback; verify installed state and vulnerability closure; document temporary mitigations and risk acceptance; improve cycle metrics.

Assign named owners for each decision and define review triggers. Tailor implementation to mission impact and architecture, but preserve the publication's named concepts so reviewers can trace local practice back to the source. Document assumptions, exclusions, inherited capabilities, and residual risk rather than presenting partial coverage as full implementation.

## Evidence to retain

Retain inventory snapshots, vendor bulletin and signature or provenance checks, applicability logic, risk ranking, test populations, compatibility results, change approval, deployment telemetry, rollback, exception and expiry, post-deployment scan, coverage denominator, and lessons learned.

Evidence must identify scope, collection date, source, owner, and covered population. Preserve raw results separately from interpretation. When remediation occurs, retain the original finding and append verification rather than rewriting history.

## Review and metrics

Review after material system, supplier, threat, mission, or organizational changes and at the stated document cycle. Metrics must include denominators and blind spots. Track overdue high-impact decisions, evidence age, exceptions approaching expiry, failed tests, and time to verified closure. Management review should focus on consequences and unresolved risk, not a context-free completion percentage.

## Failure modes

Do not measure success by patches pushed, omit unsupported assets, delay all high-risk fixes until a routine window, trust agent status without independent verification, or let emergency changes bypass later documentation and testing.

Also avoid unsupported claims based only on policy text, a product purchase, or one convenience sample. If evidence is unavailable, record the unknown, affected scope, interim safeguard, accountable owner, and decision deadline.

## Primary Sources

- [NIST Special Publication 800-40 Revision 4, Guide to Enterprise Patch Management Planning: Preventive Maintenance for an Organization’s Technology](https://csrc.nist.gov/pubs/sp/800/40/r4/final)
