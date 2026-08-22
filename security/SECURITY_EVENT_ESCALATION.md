---
title: "Security Event Escalation"
owner: "Security Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Security Event Escalation

## Purpose

Define when security-relevant observations require investigation or incident escalation.

## Escalation factors

Escalate based on potential impact, confidence, affected privilege, sensitive data, evidence of persistence, known exploitation, repeated control failure, and uncertainty.

Examples include suspected credential compromise, unauthorized privileged action, secret exposure, malicious persistence, significant security-control bypass, or unexplained sensitive-data access.

## Principles

- Preserve evidence before destructive cleanup when safe.
- Do not delay containment solely to achieve perfect classification.
- State confidence and unknowns explicitly.
- Security events that create material business impact transition into the incident-management process.

See [Security Event Escalation SOP](../sop/SECURITY_EVENT_ESCALATION_SOP.md).
