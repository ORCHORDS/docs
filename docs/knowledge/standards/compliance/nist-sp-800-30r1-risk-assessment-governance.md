---
title: "NIST SP 800-30 Rev. 1 Risk Assessment Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# NIST SP 800-30 Rev. 1 Risk Assessment Governance

## Publication and scope

This article operationalizes **NIST Special Publication 800-30 Revision 1, Guide for Conducting Risk Assessments**. It describes governance evidence and decisions; it does not make the publication mandatory or claim certification. Applicability depends on the organization, system, contract, and legal context.

## Risk model and assessment process

SP 800-30 separates threat sources, threat events, vulnerabilities and predisposing conditions, likelihood of occurrence, magnitude of impact, and resulting risk. It supports initial, periodic, and event-driven assessments and recognizes qualitative, quantitative, and semi-quantitative approaches. Assessors must state assumptions, constraints, information sources, analytic approach, and uncertainty.

## Publication-specific workflow

1. Prepare by identifying purpose, scope, assumptions, constraints, information sources, and the risk model. 2. Conduct the assessment: identify threat sources and events; identify vulnerabilities and predisposing conditions; determine likelihood; determine impact; determine risk. 3. Communicate results to decision makers in a form that preserves uncertainty and scenario context. 4. Maintain the assessment when assets, threats, vulnerabilities, controls, or mission consequences change.

Assign named owners for each decision and define review triggers. Tailor implementation to mission impact and architecture, but preserve the publication's named concepts so reviewers can trace local practice back to the source. Document assumptions, exclusions, inherited capabilities, and residual risk rather than presenting partial coverage as full implementation.

## Evidence to retain

Keep the assessment plan, threat-source and event catalog, vulnerability observations, likelihood and impact scales, scenario worksheets, risk determinations, uncertainty notes, reviewer challenges, risk-owner decisions, and update triggers. A risk score without its threat event, affected asset, assumptions, and rationale is not reproducible.

Evidence must identify scope, collection date, source, owner, and covered population. Preserve raw results separately from interpretation. When remediation occurs, retain the original finding and append verification rather than rewriting history.

## Review and metrics

Review after material system, supplier, threat, mission, or organizational changes and at the stated document cycle. Metrics must include denominators and blind spots. Track overdue high-impact decisions, evidence age, exceptions approaching expiry, failed tests, and time to verified closure. Management review should focus on consequences and unresolved risk, not a context-free completion percentage.

## Failure modes

Do not equate a vulnerability severity score with organizational risk. Do not omit threat events, collapse likelihood and impact into unexplained colors, treat incomplete intelligence as certainty, or reuse one assessment unchanged across systems with different missions.

Also avoid unsupported claims based only on policy text, a product purchase, or one convenience sample. If evidence is unavailable, record the unknown, affected scope, interim safeguard, accountable owner, and decision deadline.

## Primary Sources

- [NIST Special Publication 800-30 Revision 1, Guide for Conducting Risk Assessments](https://csrc.nist.gov/pubs/sp/800/30/r1/final)
