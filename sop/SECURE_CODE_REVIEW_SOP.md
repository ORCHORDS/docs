---
title: "SOP: Secure Code Review"
owner: "Engineering Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# SOP: Secure Code Review

## Trigger

Use for material software changes, with additional depth for security-sensitive
code.

## Procedure

1. Confirm purpose and acceptance criteria.
2. Identify changed trust boundaries, permissions, data flows, or dependencies.
3. Review authorization and input/output handling.
4. Review secrets, cryptography, logging, and error behavior.
5. Review failure modes, rollback, and migration behavior.
6. Examine tests for both expected and abuse cases.
7. Check dependency and generated-code changes.
8. Resolve material findings before approval or record an approved exception.
9. Preserve review discussion in the change record.

## Evidence

Use [Code Review Checklist](../templates/CODE_REVIEW_CHECKLIST_TEMPLATE.md).
