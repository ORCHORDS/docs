---
title: "NIST SP 800-207 Zero Trust Architecture"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# NIST SP 800-207 Zero Trust Architecture

## Publication and scope

This article operationalizes **NIST Special Publication 800-207, Zero Trust Architecture**. It describes governance evidence and decisions; it does not make the publication mandatory or claim certification. Applicability depends on the organization, system, contract, and legal context.

## Tenets, logical components, and deployment models

Zero trust grants no implicit trust based on network location or ownership. Access is per session, least privilege, dynamically determined from identity, device, resource, environment, and threat data. Logical components include the policy engine, policy administrator, policy enforcement point, policy information sources, identity management, PKI, threat intelligence, logs, and security analytics. Deployment approaches include enhanced identity governance, micro-segmentation, software-defined perimeter, and device-agent or gateway models.

## Publication-specific workflow

Inventory subjects, devices, data, applications, and services; map transaction flows; establish strong identities and device posture; define resource-centric policies; place enforcement points; integrate information sources into the trust algorithm; pilot a narrow workflow; test allow, deny, revocation, degraded telemetry, and administrator compromise; expand while monitoring policy decisions.

Assign named owners for each decision and define review triggers. Tailor implementation to mission impact and architecture, but preserve the publication's named concepts so reviewers can trace local practice back to the source. Document assumptions, exclusions, inherited capabilities, and residual risk rather than presenting partial coverage as full implementation.

## Evidence to retain

Keep resource and subject inventories, flow maps, policy-engine rules, trust-algorithm inputs, identity and device bindings, policy-administrator actions, enforcement-point configurations, certificates, allow and deny decisions, telemetry lineage, exception approvals, adversarial tests, and migration decisions.

Evidence must identify scope, collection date, source, owner, and covered population. Preserve raw results separately from interpretation. When remediation occurs, retain the original finding and append verification rather than rewriting history.

## Review and metrics

Review after material system, supplier, threat, mission, or organizational changes and at the stated document cycle. Metrics must include denominators and blind spots. Track overdue high-impact decisions, evidence age, exceptions approaching expiry, failed tests, and time to verified closure. Management review should focus on consequences and unresolved risk, not a context-free completion percentage.

## Failure modes

Do not relabel VPN access as zero trust, make network location the deciding signal, issue broad long-lived authorization, trust unmanaged telemetry, create unenforced policy, or centralize decisions without resilience and fail-safe behavior.

Also avoid unsupported claims based only on policy text, a product purchase, or one convenience sample. If evidence is unavailable, record the unknown, affected scope, interim safeguard, accountable owner, and decision deadline.

## Primary Sources

- [NIST Special Publication 800-207, Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final)
