---
title: "CISA Secure by Default Product Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# CISA Secure by Default Product Governance

## Publication and scope

This article operationalizes **CISA Secure by Design guidance: Secure by Default**. It describes governance evidence and decisions; it does not make the publication mandatory or claim certification. Applicability depends on the organization, system, contract, and legal context.

## Safe product defaults

Secure by Default places responsibility on manufacturers to make the most important security controls available and enabled without added cost or expert configuration. CISA examples include eliminating default passwords, enabling multifactor authentication and logging, supporting single sign-on, reducing dangerous legacy features, and making security settings understandable. Secure by Default complements the broader Secure by Design principles of ownership, transparency, and leadership commitment.

## Publication-specific workflow

Define abuse cases before defaults; select the safest usable initial state; eliminate shared credentials; require secure enrollment; enable useful logs and update paths; gate risky legacy protocols behind explicit action; test fresh installs, upgrades, recovery, and tenant creation; review telemetry and support cases for users weakening defaults; require executive approval for commercial exceptions.

Assign named owners for each decision and define review triggers. Tailor implementation to mission impact and architecture, but preserve the publication's named concepts so reviewers can trace local practice back to the source. Document assumptions, exclusions, inherited capabilities, and residual risk rather than presenting partial coverage as full implementation.

## Evidence to retain

Preserve default configuration specifications, threat and usability studies, fresh-install and upgrade tests, release-gate results, legacy-feature decisions, cost and licensing review, opt-out telemetry, customer notices, exceptions, and regression tests.

Evidence must identify scope, collection date, source, owner, and covered population. Preserve raw results separately from interpretation. When remediation occurs, retain the original finding and append verification rather than rewriting history.

## Review and metrics

Review after material system, supplier, threat, mission, or organizational changes and at the stated document cycle. Metrics must include denominators and blind spots. Track overdue high-impact decisions, evidence age, exceptions approaching expiry, failed tests, and time to verified closure. Management review should focus on consequences and unresolved risk, not a context-free completion percentage.

## Failure modes

Do not advertise secure defaults that require premium licensing, enable a control only in documentation, preserve unsafe behavior solely for compatibility, use hidden opt-outs, or shift routine hardening work to every customer.

Also avoid unsupported claims based only on policy text, a product purchase, or one convenience sample. If evidence is unavailable, record the unknown, affected scope, interim safeguard, accountable owner, and decision deadline.

## Primary Sources

- [CISA Secure by Design guidance: Secure by Default](https://www.cisa.gov/securebydesign)
