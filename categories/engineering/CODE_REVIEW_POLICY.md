---
title: "Code Review Policy"
owner: "Engineering Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Code Review Policy

## Purpose

Define review expectations for software and automation changes.

## Principles

Review is an independent risk-control activity, not a formatting ritual.

Reviewers SHOULD evaluate:

- correctness against acceptance criteria;
- security and privacy impact;
- failure modes and rollback;
- tests and test quality;
- dependency changes;
- compatibility and migration behavior;
- observability and sensitive-data handling;
- maintainability and unnecessary complexity.

## Higher-risk changes

Sensitive or high-impact changes require additional reviewer expertise or a
second approval where risk warrants it. Authors should not approve their own
change as the sole independent review.

## Review evidence

Material review concerns and their resolution should remain visible in the
change history.

See [Secure Code Review SOP](../sop/SECURE_CODE_REVIEW_SOP.md) and
[Code Review Checklist](../templates/CODE_REVIEW_CHECKLIST_TEMPLATE.md).
