---
title: "SOP: Document Review"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# SOP: Document Review

## Trigger

Use for scheduled review, standards changes, ownership changes, audit/incident findings, or material content updates.

## Roles

- **Document owner:** accountable for accuracy.
- **Reviewer:** independently checks usability and claims.
- **Documentation Maintainer:** checks structure, links, metadata, and publication boundary.
- **Security reviewer:** required for security-sensitive content.

## Procedure

1. Confirm owner, status, last review, next review, and review cycle.
2. Read the document end-to-end as a new reader.
3. Validate every factual claim that can become stale.
4. Verify external standards against primary sources.
5. Mark drafts as drafts; do not silently treat draft standards as final.
6. Remove obsolete implementation detail and duplicate policy.
7. Check the public-safety boundary in [Document Control](../governance/DOCUMENT_CONTROL.md).
8. Validate relative links.
9. Run `python .github/scripts/check_docs.py`.
10. Open a pull request describing sources checked and material changes.
11. Obtain required review.
12. Set review metadata to the approval date and computed next review.

## Evidence

The pull request is the review record and identifies major sources checked, reviewers, and unresolved follow-up.

## Completion criteria

Automated checks pass, unsupported assurance claims are removed, review metadata is current, and owner approval is recorded.
