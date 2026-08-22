---
title: "Release Management Policy"
owner: "Release Manager"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Release Management Policy

## Purpose

Ensure releases are authorized, traceable, verifiable, supportable, and
recoverable.

## Release readiness

Before a production release, confirm as applicable:

- intended scope is understood;
- required reviews and tests passed;
- security findings are addressed or formally accepted;
- migration risk is understood;
- operational monitoring is ready;
- rollback or containment is feasible;
- release notes are accurate;
- artifact integrity can be verified;
- responsible people know the release window and escalation path.

## Separation of duties

High-impact releases should not rely on one person to author, approve, and
promote the same change without independent review.

## Artifacts

Release artifacts should be traceable to a source revision. Higher-assurance
releases may require signing, provenance, and SBOM evidence.

## Emergency releases

Emergency releases may compress approval steps when delay is riskier, but they
still require a named owner, minimum verification, containment/rollback plan,
and retrospective review.

Follow [Release SOP](../sop/RELEASE_SOP.md).
