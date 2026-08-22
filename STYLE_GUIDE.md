---
title: "Documentation Style Guide"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "180 days"
next-review: "2027-02-18"
---

# Documentation Style Guide

## Goals

Documentation should be accurate, concise, searchable, accessible, and usable
during normal work and under pressure.

## Writing rules

- Lead with the purpose and scope.
- Use short sections with descriptive headings.
- Prefer active voice and direct verbs.
- Define acronyms on first use.
- Separate policy requirements from examples.
- Use tables for comparisons, roles, thresholds, and evidence.
- Use numbered steps only when order matters.
- Avoid decorative complexity, inflated claims, and vague words such as
  "best-in-class", "fully secure", or "100% compliant".
- State uncertainty explicitly.

## Requirement words

Use **MUST**, **SHOULD**, and **MAY** only for normative statements. Avoid
using them for marketing emphasis.

## Dates and versions

- Use ISO dates (`YYYY-MM-DD`) for review metadata.
- Name versions when a referenced framework is versioned.
- Mark draft sources as draft.
- Do not use "latest" in a controlled requirement unless the process also
  defines how the latest version is verified.

## Links

- Prefer primary sources.
- Use relative links for files in this repository.
- Do not link to private resources from public documents.
- Links must explain their destination; avoid "click here".

## Accessibility

- Use meaningful headings in order.
- Give images useful alternative text.
- Do not convey meaning by color alone.
- Keep table structure simple.
- Use descriptive link text.
- Prefer plain language where legal or technical precision does not require
  specialized terminology.

See [ACCESSIBILITY_POLICY.md](./ACCESSIBILITY_POLICY.md).

## SOP format

Every SOP should contain:

1. Purpose
2. Scope and trigger
3. Roles
4. Preconditions/inputs
5. Procedure
6. Decision or escalation points
7. Evidence/records
8. Metrics or completion criteria
9. Exceptions
10. Related documents

## Claims

Do not state that a control exists merely because a policy requires it. Use
"required", "implemented", "planned", or "not applicable" accurately.

## Public-safe examples

Examples must use fictitious values and generic roles. Never paste real
credentials, private endpoints, internal identifiers, customer data, or
sensitive incident details into examples.
