---
title: "OWASP API Security API1:2023 BOLA Verification"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# OWASP API Security API1:2023 BOLA Verification

## Pinned source and scope
OWASP API Security Top 10 **2023**, **API1:2023 Broken Object Level Authorization**. This article uses the named version and identifiers; do not combine evidence from another edition without a migration record.

## Control interpretation
Every endpoint that accepts an object identifier must authorize the authenticated principal for that specific object and action. UUID unpredictability is not authorization. Apply checks after canonical lookup for path, query, body, header, GraphQL node, batch member, export, nested object, and indirect file references. Tenant, owner, delegated relationship, object state, and operation all belong in the decision.

## Domain-specific procedure
Create two users in the same tenant and one in another tenant, with distinguishable objects. Swap identifiers across GET, update, delete, batch, GraphQL aliases, exports, attachments, and soft-deleted records. Try parent-authorized/child-unauthorized combinations and race ownership changes. Require consistent denial without existence leakage and verify no asynchronous side effect occurs.

## Evidence and decision
Retain the subject/object/action tuple, both owners, original and substituted identifiers, response, datastore side effects, and asynchronous job output. A uniform 404 may be acceptable only when no unauthorized effect occurs.

## Failure modes
UUID reliance, tenant-only checks, list filtering without detail authorization, and batch authorization applied only to the first member are failures.

## Sources
- [Pinned canonical source](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
