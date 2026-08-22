---
title: "Security Architecture Principles"
owner: "Security Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Security Architecture Principles

## Purpose

Set high-level security architecture principles while keeping implementation architecture private.

## Principles

- Explicitly authenticate and authorize sensitive access.
- Prefer least privilege and deny-by-default behavior.
- Minimize implicit trust based on location or ownership alone.
- Reduce unnecessary attack surface and privilege paths.
- Design for containment and recovery, not only prevention.
- Protect secrets and high-value data throughout their lifecycle.
- Make important security state observable.
- Prefer simple, reviewable trust boundaries over hidden coupling.
- Assume dependencies and controls can fail.

## Engineering

Material trust-boundary decisions should be documented privately where necessary and informed by [Secure Design and Threat Modeling](../engineering/SECURE_DESIGN_THREAT_MODELING.md).
