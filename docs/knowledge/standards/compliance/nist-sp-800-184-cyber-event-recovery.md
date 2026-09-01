---
title: "NIST SP 800-184 Cybersecurity Event Recovery"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# NIST SP 800-184 Cybersecurity Event Recovery

## Publication and scope

This article operationalizes **NIST Special Publication 800-184, Guide for Cybersecurity Event Recovery**. It describes governance evidence and decisions; it does not make the publication mandatory or claim certification. Applicability depends on the organization, system, contract, and legal context.

## Recovery planning, execution, and improvement

SP 800-184 focuses on recovering from cybersecurity events and maps recovery to CSF Recover categories: Recovery Planning, Improvements, and Communications. It distinguishes strategic, tactical, and operational recovery planning and stresses dependencies, restoration priorities, integrity, communications, metrics, and lessons learned.

## Publication-specific workflow

Define recovery objectives and service priorities; identify internal, external, and supply-chain dependencies; create playbooks for credible scenarios; establish decision authority and communication channels; test backups and alternate capabilities; during recovery assess damage, contain dependencies, select a trusted restoration point, rebuild and validate, communicate status, and return services in approved order; capture improvements.

Assign named owners for each decision and define review triggers. Tailor implementation to mission impact and architecture, but preserve the publication's named concepts so reviewers can trace local practice back to the source. Document assumptions, exclusions, inherited capabilities, and residual risk rather than presenting partial coverage as full implementation.

## Evidence to retain

Retain business-impact and dependency analyses, recovery plans and playbooks, backup inventories, immutability and restore tests, exercise results, incident recovery timeline, restoration-point decision, rebuilt asset records, malware and integrity checks, business validation, communications, metrics, and after-action improvements.

Evidence must identify scope, collection date, source, owner, and covered population. Preserve raw results separately from interpretation. When remediation occurs, retain the original finding and append verification rather than rewriting history.

## Review and metrics

Review after material system, supplier, threat, mission, or organizational changes and at the stated document cycle. Metrics must include denominators and blind spots. Track overdue high-impact decisions, evidence age, exceptions approaching expiry, failed tests, and time to verified closure. Management review should focus on consequences and unresolved risk, not a context-free completion percentage.

## Failure modes

Availability alone does not prove recovery. Avoid restoring compromised images, reconnecting before eradication, overlooking identity and management-plane dependencies, promising untested recovery times, failing to validate data integrity, or closing recovery before business owners confirm service outcomes.

Also avoid unsupported claims based only on policy text, a product purchase, or one convenience sample. If evidence is unavailable, record the unknown, affected scope, interim safeguard, accountable owner, and decision deadline.

## Primary Sources

- [NIST Special Publication 800-184, Guide for Cybersecurity Event Recovery](https://csrc.nist.gov/pubs/sp/800/184/final)
