---
title: "CISA Memory Safe Languages Roadmap Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# CISA Memory Safe Languages Roadmap Governance

## Publication and scope

This article operationalizes **CISA The Case for Memory Safe Roadmaps**. It describes governance evidence and decisions; it does not make the publication mandatory or claim certification. Applicability depends on the organization, system, contract, and legal context.

## Measurable memory-safety transition

CISA and partners ask software manufacturers to publish roadmaps explaining how they will reduce memory-safety vulnerabilities through memory-safe languages. A credible roadmap addresses language choices, existing code, dependencies, interoperability, staffing, milestones, metrics, and constraints. It should distinguish new development, rewrites, wrappers or isolation, and residual unsafe code.

## Publication-specific workflow

Inventory languages and memory-unsafe components; correlate recurring defects with exploitability and product criticality; require memory-safe choices for feasible new work; rank legacy components for replacement or isolation; evaluate dependencies and foreign-function interfaces; fund training and build-system changes; publish milestones; measure new unsafe code, migrated code, vulnerability trends, and exceptions.

Assign named owners for each decision and define review triggers. Tailor implementation to mission impact and architecture, but preserve the publication's named concepts so reviewers can trace local practice back to the source. Document assumptions, exclusions, inherited capabilities, and residual risk rather than presenting partial coverage as full implementation.

## Evidence to retain

Keep language and component inventory, vulnerability history, criticality model, feasibility studies, architecture decisions, roadmap versions, milestone funding, compiler and build controls, migration tests, unsafe-code exceptions, dependency plans, and outcome metrics.

Evidence must identify scope, collection date, source, owner, and covered population. Preserve raw results separately from interpretation. When remediation occurs, retain the original finding and append verification rather than rewriting history.

## Review and metrics

Review after material system, supplier, threat, mission, or organizational changes and at the stated document cycle. Metrics must include denominators and blind spots. Track overdue high-impact decisions, evidence age, exceptions approaching expiry, failed tests, and time to verified closure. Management review should focus on consequences and unresolved risk, not a context-free completion percentage.

## Failure modes

Do not count bindings as safety when unsafe code remains exposed, mandate rewrites without dependency analysis, measure only lines migrated, hide exceptions, or imply a language choice eliminates logic and design vulnerabilities.

Also avoid unsupported claims based only on policy text, a product purchase, or one convenience sample. If evidence is unavailable, record the unknown, affected scope, interim safeguard, accountable owner, and decision deadline.

## Primary Sources

- [CISA The Case for Memory Safe Roadmaps](https://www.cisa.gov/resources-tools/resources/case-memory-safe-roadmaps)
