---
title: "Document Control"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Document Control

## Purpose

This policy keeps public documentation accurate, reviewable, discoverable,
public-safe, and resistant to stale claims.

## Controlled-document requirements

Each controlled Markdown document must identify:

- title;
- owner role;
- approval status;
- public classification;
- last review date;
- review cycle;
- next review date.

The repository quality check validates these fields.

## Public-safety boundary

Do not publish credentials, tokens, private endpoints, private topology,
customer information, internal access-control membership, unannounced work,
unresolved exploit detail, or unsupported assurance claims.

Provider names and implementation details should appear only when necessary for
a public procedure. Prefer provider-neutral controls.

## Evidence language

- **MUST / SHALL**: mandatory requirement.
- **SHOULD**: expected unless a documented reason justifies another approach.
- **MAY**: permitted option.
- **Implemented**: supported by current evidence.
- **Planned**: approved but not yet implemented.
- **Target**: desired outcome, not a current fact.

Normative terms follow RFC 2119 and RFC 8174 conventions.

## Review triggers

Review before the scheduled date when a referenced standard materially changes,
an incident or audit identifies a gap, ownership changes, a control changes,
repeated confusion indicates usability problems, or a linked source becomes
obsolete.

## Change rules

- Changes use pull requests.
- The document owner or delegated reviewer approves substantive changes.
- Security-sensitive documents require security review.
- Broken links, placeholders, unsupported claims, and implementation leakage
  block merge.
- Superseded documents are deleted or explicitly deprecated.

## Review procedure

Follow [Document Review SOP](../sop/DOCUMENT_REVIEW_SOP.md).
