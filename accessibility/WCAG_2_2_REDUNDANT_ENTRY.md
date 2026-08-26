---
title: "WCAG 2.2 Redundant Entry Governance"
owner: "Accessibility Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# WCAG 2.2 Redundant Entry Governance

## Source

W3C Web Accessibility Initiative — Understanding Success Criterion 3.3.7 Redundant Entry: https://www.w3.org/WAI/WCAG22/Understanding/redundant-entry.html

WCAG 2.2 Success Criterion 3.3.7 is Level A. Its purpose is to reduce unnecessary repeated data entry within the same process.

## Requirement

When information previously entered by, or provided to, the user is required again in the same process, the experience should either:

- auto-populate that information; or
- make the previous information available for the user to select.

The W3C criterion includes exceptions when re-entry is essential, is needed to ensure the security of the content, or when the earlier information is no longer valid.

## Governance expectations

- Multi-step forms should identify fields that request the same information more than once.
- Repeated information should be carried forward or offered for selection when doing so is safe and appropriate.
- Browser autocomplete alone should not be treated as satisfying this control; the application flow itself should manage redundant entry where the criterion applies.
- Implementations must not introduce new privacy exposure merely to avoid repeated entry.
- Security-sensitive re-entry should document why the exception is necessary.

## Verification

Review representative multi-step user journeys and record:

- repeated fields;
- whether earlier values are available without retyping;
- any security or validity exception relied upon;
- privacy impact of retained values; and
- manual keyboard and assistive-technology results.

Conformance claims require evidence from the implemented flow, not this policy document alone.
