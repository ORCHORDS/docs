---
title: "Security Test Coverage Governance"
owner: "Security Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-23"
review-cycle: "90 days"
next-review: "2026-11-21"
---

# Security Test Coverage Governance

## Purpose

Align security testing with material attack surfaces and changes rather than relying on a single test type.

## Requirements

Coverage SHOULD consider architecture, authentication and authorization, input handling, data access, dependency risk, privileged operations, abuse cases, configuration, release-critical changes, and prior findings.

Automated scanning is useful evidence but does not replace manual or scenario-based review where judgment is required.

Known untested high-risk areas should remain visible as assurance gaps.
