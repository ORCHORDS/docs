---
title: "Access Management Policy"
owner: "Security and Operations Leads"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Access Management Policy

## Principles

- Named identities over shared identities.
- Least privilege.
- Need-to-know access to sensitive information.
- Strong authentication for privileged access where supported.
- Prompt removal of access that is no longer needed.
- Separation of duties for high-impact actions where practical.
- Periodic review of privileged and sensitive access.

## Joiner, mover, leaver controls

Access is granted from approved role need, adjusted when duties change, and
revoked promptly on departure or loss of need.

## Privileged access

Privileged access should:

- be limited to authorized roles;
- use separate administrative identities where appropriate;
- avoid long-lived standing privilege when just-in-time access is practical;
- be logged by the platform where supported;
- receive more frequent review than ordinary access.

## Service identities

Machine and automation identities require an owner, defined purpose, minimum
scope, protected credentials, and lifecycle review.

## Reviews

Follow [Access Review SOP](../sop/ACCESS_REVIEW_SOP.md).
