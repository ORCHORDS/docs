---
title: "NIST SP 800-137 Information Security Continuous Monitoring"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# NIST SP 800-137 Information Security Continuous Monitoring

## Publication and scope

This article operationalizes **NIST Special Publication 800-137, Information Security Continuous Monitoring (ISCM) for Federal Information Systems and Organizations**. It describes governance evidence and decisions; it does not make the publication mandatory or claim certification. Applicability depends on the organization, system, contract, and legal context.

## ISCM strategy and program

ISCM gives officials ongoing awareness of information security, vulnerabilities, threats, and control effectiveness to support risk decisions. Its process defines an ISCM strategy; establishes the program; implements it; analyzes data and reports findings; responds to findings; and reviews and updates the strategy and program. Monitoring frequencies are risk based, and automation supports—not replaces—analysis.

## Publication-specific workflow

Define metrics, frequencies, assessment methods, reporting requirements, responsible roles, and escalation thresholds at organization and system levels. Establish architecture and tools that collect trustworthy data. Analyze results in mission context, report to people with response authority, initiate remediation or risk acceptance, and revise frequencies when threats, controls, or systems change.

Assign named owners for each decision and define review triggers. Tailor implementation to mission impact and architecture, but preserve the publication's named concepts so reviewers can trace local practice back to the source. Document assumptions, exclusions, inherited capabilities, and residual risk rather than presenting partial coverage as full implementation.

## Evidence to retain

Keep the ISCM strategy, system monitoring plans, metric definitions, data feeds, collection health, assessment schedules, control status, asset and vulnerability data, dashboards, alerts, analyst conclusions, response tickets, risk decisions, and strategy-review minutes. Measure blind spots and failed collections as well as findings.

Evidence must identify scope, collection date, source, owner, and covered population. Preserve raw results separately from interpretation. When remediation occurs, retain the original finding and append verification rather than rewriting history.

## Review and metrics

Review after material system, supplier, threat, mission, or organizational changes and at the stated document cycle. Metrics must include denominators and blind spots. Track overdue high-impact decisions, evidence age, exceptions approaching expiry, failed tests, and time to verified closure. Management review should focus on consequences and unresolved risk, not a context-free completion percentage.

## Failure modes

Continuous monitoring is not continuous scanning. Avoid collecting data with no decision path, using fixed frequencies unrelated to risk, assuming dashboard green means control effectiveness, excluding manual controls, ignoring sensor health, or retaining stale system inventories.

Also avoid unsupported claims based only on policy text, a product purchase, or one convenience sample. If evidence is unavailable, record the unknown, affected scope, interim safeguard, accountable owner, and decision deadline.

## Primary Sources

- [NIST Special Publication 800-137, Information Security Continuous Monitoring (ISCM) for Federal Information Systems and Organizations](https://csrc.nist.gov/pubs/sp/800/137/final)
