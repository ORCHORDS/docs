---
title: "Engineering Standards"
owner: "Engineering Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Engineering Standards

## Purpose

Define company-wide expectations for maintainable, testable, secure, and
reviewable software without publishing system-specific architecture.

## Core expectations

Engineering work MUST:

- have a clear purpose and acceptance criteria;
- be tracked in version control;
- be reviewable through a change proposal or pull request;
- include tests appropriate to impact and failure modes;
- avoid embedding secrets;
- handle errors intentionally;
- produce useful diagnostic information without exposing sensitive data;
- document material operational or security behavior;
- preserve a safe rollback or containment path for high-impact changes.

## Design quality

Prefer small cohesive components, explicit interfaces and ownership, least
privilege, secure defaults, bounded resource use, idempotent operations where
practical, backward-compatible migrations, and observability designed with the
feature.

Important design decisions should record context, options, decision, tradeoffs,
and consequences.

## Change risk

Classify changes by blast radius, data sensitivity, reversibility, dependency
risk, and novelty. Higher-risk changes require stronger review, verification,
rollout controls, and rollback evidence.

## Secure development

Use the [Security Policy](../security/SECURITY_POLICY.md),
[Secure Design and Threat Modeling](./SECURE_DESIGN_THREAT_MODELING.md),
[Open Source and Dependency Policy](./OPEN_SOURCE_DEPENDENCY_POLICY.md),
[Source Control Policy](./SOURCE_CONTROL_POLICY.md),
[CI/CD Policy](./CI_CD_POLICY.md), and
[Software Supply Chain Policy](./SOFTWARE_SUPPLY_CHAIN.md).

OWASP ASVS 5.0.0 may define application-security verification requirements.
NIST SSDF 1.1 is the stable secure-development reference; SSDF 1.2 is monitored
as a draft until finalized.

## Definition of done

A change is not done until required tests pass, review is complete, material
documentation is updated, security/privacy implications are addressed, and
operational rollout/rollback needs are understood.
