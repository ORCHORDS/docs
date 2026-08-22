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

Do not publish:

- credentials, tokens, keys, secrets, recovery codes, or sensitive fragments;
- private hostnames, private endpoints, network topology, account identifiers,
  tenant identifiers, internal IP addresses, or non-public environment names;
- customer information or personal data;
- internal access-control membership;
- unannounced commercial or product information;
- exploit instructions for an unresolved vulnerability;
- operational details that materially lower the cost of attacking the company;
- claims of certification, audit success, penetration testing, bug bounty
  coverage, or implemented controls without current evidence.

Provider names and implementation details should appear only when they are
necessary for a public procedure. Prefer provider-neutral controls.

## Evidence language

Use precise status language:

- **MUST / SHALL**: mandatory policy requirement.
- **SHOULD**: expected unless a documented reason justifies another approach.
- **MAY**: permitted option.
- **Implemented**: supported by current evidence.
- **Planned**: approved but not yet implemented.
- **Target**: desired outcome, not a current fact.

Normative terms follow RFC 2119 and RFC 8174 conventions.

## Review triggers

Review a document before its scheduled date when any of the following occurs:

- a referenced standard materially changes;
- an incident or audit identifies a documentation gap;
- ownership or process changes;
- a control is added, removed, or materially modified;
- repeated user confusion indicates the procedure is not usable;
- a linked source becomes unavailable or obsolete.

## Change rules

- Changes use pull requests.
- The document owner or delegated reviewer approves substantive changes.
- Security-sensitive documents require Security Lead review.
- Broken links, placeholders, unsupported claims, and project-specific
  implementation detail block merge.
- Superseded documents are deleted or clearly marked archived; duplicate
  policy sources are not maintained in parallel.

## Quality bar

A controlled document should answer:

1. Why does this exist?
2. Who owns it?
3. When does it apply?
4. What must be done?
5. What evidence proves it was done?
6. What happens when the normal path fails?
7. When will this document be reviewed again?

## Review procedure

Follow [Document Review SOP](./sop/DOCUMENT_REVIEW_SOP.md).
